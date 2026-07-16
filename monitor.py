from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

import config
import db
import emailer

LEVEL_ORDER = {"INFORMATIVO": 1, "ATENCION": 2, "CRITICO": 3}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def level_for_distance(distance_km: float, radius_km: float) -> str:
    if distance_km <= min(config.ALERT_CRITICAL_KM, radius_km):
        return "CRITICO"
    if distance_km <= min(config.ALERT_ATTENTION_KM, radius_km):
        return "ATENCION"
    return "INFORMATIVO"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def local_date_str() -> str:
    return (now_utc() + timedelta(hours=config.EMAIL_TIMEZONE_OFFSET_HOURS)).strftime("%Y-%m-%d")


def local_hour() -> int:
    return int((now_utc() + timedelta(hours=config.EMAIL_TIMEZONE_OFFSET_HOURS)).strftime("%H"))


def foco_external_id(source: str, row: dict[str, str]) -> str:
    raw = "|".join(
        [
            source,
            row.get("latitude", ""),
            row.get("longitude", ""),
            row.get("acq_date", ""),
            row.get("acq_time", ""),
            row.get("satellite", ""),
            row.get("instrument", ""),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def fetch_firms_source(source: str) -> tuple[list[dict[str, str]], str]:
    if not config.FIRMS_MAP_KEY:
        return [], "FIRMS_MAP_KEY no configurada"
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{config.FIRMS_MAP_KEY}/{source}/{config.FIRMS_AREA_BBOX}/{config.FIRMS_DAY_RANGE}"
    resp = requests.get(url, timeout=config.FIRMS_REQUEST_TIMEOUT_SECONDS)
    if resp.status_code != 200:
        return [], f"{source}: HTTP {resp.status_code} {resp.text[:200]}"
    text = resp.text.strip()
    if not text or text.lower().startswith("no data"):
        return [], ""
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        try:
            float(row.get("latitude", ""))
            float(row.get("longitude", ""))
        except Exception:
            continue
        row["_source"] = source
        rows.append(row)
    return rows, ""


def fetch_all_firms() -> tuple[list[dict[str, str]], list[str]]:
    all_rows: list[dict[str, str]] = []
    errors: list[str] = []
    for source in config.FIRMS_SOURCES:
        rows, err = fetch_firms_source(source)
        if err:
            errors.append(err)
        all_rows.extend(rows)
    return all_rows, errors


def save_focos(rows: list[dict[str, str]]) -> int:
    if not rows:
        return 0
    inserted = 0
    sql = """
        INSERT INTO focos(external_id, source, lat, lon, acq_date, acq_time, satellite, confidence, frp, daynight, raw)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT(external_id) DO NOTHING
    """
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            for row in rows:
                source = row.get("_source") or "FIRMS"
                ext = foco_external_id(source, row)
                cur.execute(
                    sql,
                    (
                        ext,
                        source,
                        float(row.get("latitude")),
                        float(row.get("longitude")),
                        row.get("acq_date", ""),
                        row.get("acq_time", ""),
                        row.get("satellite", ""),
                        row.get("confidence", ""),
                        row.get("frp", ""),
                        row.get("daynight", ""),
                        json.dumps(row),
                    ),
                )
                inserted += cur.rowcount
    return inserted


def build_alert_message(zone: dict[str, Any], level: str, foco_count: int, nearest: dict[str, Any], distance: float) -> str:
    plural = "foco" if foco_count == 1 else "focos"
    return (
        f"CampoSeguro informa que se detectaron {foco_count} {plural} de calor dentro del radio configurado "
        f"para la zona {zone['name']}, municipio {zone.get('municipio') or zone['name']}. "
        f"La distancia mínima registrada es {distance:.2f} km. Nivel: {level}. "
        "Recomendación: verificar con fuentes locales, revisar condiciones de viento y mantener seguimiento preventivo. "
        "Esta información es de carácter informativo y debe ser validada por responsables locales o autoridades competentes."
    )


def recalc_alerts() -> int:
    zones = db.execute(
        """
        SELECT z.*, u.name AS user_name, u.email AS user_email, u.phone AS user_phone
        FROM zones z
        JOIN users u ON u.id=z.user_id
        WHERE z.active=TRUE AND u.active=TRUE AND u.role='client'
        ORDER BY z.user_id, z.name
        """,
        fetch="all",
    ) or []

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM zone_alerts")

    created = 0
    for zone in zones:
        radius = float(zone["radius_km"] or config.DEFAULT_ZONE_RADIUS_KM)
        lat = float(zone["lat"])
        lon = float(zone["lon"])
        lat_delta = max(radius / 111.0, 0.05)
        lon_delta = max(radius / (111.0 * max(math.cos(math.radians(lat)), 0.2)), 0.05)
        candidates = db.execute(
            """
            SELECT id, source, lat, lon, acq_date, acq_time, satellite, confidence, frp
            FROM focos
            WHERE lat BETWEEN %s AND %s AND lon BETWEEN %s AND %s
            """,
            (lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta),
            fetch="all",
        ) or []
        inside: list[tuple[float, dict[str, Any]]] = []
        for foco in candidates:
            d = haversine_km(lat, lon, float(foco["lat"]), float(foco["lon"]))
            if d <= radius:
                inside.append((d, foco))
        if not inside:
            continue
        inside.sort(key=lambda item: item[0])
        min_distance, nearest = inside[0]
        foco_count = len(inside)
        max_level = "INFORMATIVO"
        for d, _f in inside:
            lvl = level_for_distance(d, radius)
            if LEVEL_ORDER[lvl] > LEVEL_ORDER[max_level]:
                max_level = lvl
        latest = max(f"{f.get('acq_date','')} {f.get('acq_time','')}" for _d, f in inside).strip()
        message = build_alert_message(zone, max_level, foco_count, nearest, min_distance)
        db.execute(
            """
            INSERT INTO zone_alerts(user_id, zone_id, level, foco_count, nearest_foco_id, min_distance_km, latest_detection, message, active)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
            ON CONFLICT(zone_id) DO UPDATE SET
                level=EXCLUDED.level,
                foco_count=EXCLUDED.foco_count,
                nearest_foco_id=EXCLUDED.nearest_foco_id,
                min_distance_km=EXCLUDED.min_distance_km,
                latest_detection=EXCLUDED.latest_detection,
                message=EXCLUDED.message,
                active=TRUE,
                calculated_at=now()
            """,
            (zone["user_id"], zone["id"], max_level, foco_count, nearest["id"], min_distance, latest, message),
        )
        created += 1
    return created


def user_alert_summary(user_id: int) -> dict[str, Any] | None:
    user = db.execute("SELECT * FROM users WHERE id=%s AND active=TRUE", (user_id,), fetch="one")
    if not user:
        return None
    alerts = db.execute(
        """
        SELECT a.*, z.name AS zone_name, z.municipio, z.radius_km, f.source, f.lat AS foco_lat, f.lon AS foco_lon, f.acq_date, f.acq_time
        FROM zone_alerts a
        JOIN zones z ON z.id=a.zone_id
        LEFT JOIN focos f ON f.id=a.nearest_foco_id
        WHERE a.user_id=%s AND a.active=TRUE
        ORDER BY CASE a.level WHEN 'CRITICO' THEN 3 WHEN 'ATENCION' THEN 2 ELSE 1 END DESC,
                 a.min_distance_km ASC
        """,
        (user_id,),
        fetch="all",
    ) or []
    if not alerts:
        return None
    max_level = max((a["level"] for a in alerts), key=lambda lvl: LEVEL_ORDER.get(lvl, 0))
    critical = sum(1 for a in alerts if a["level"] == "CRITICO")
    attention = sum(1 for a in alerts if a["level"] == "ATENCION")
    info = sum(1 for a in alerts if a["level"] == "INFORMATIVO")
    min_distance = min(float(a["min_distance_km"] or 999999) for a in alerts)
    return {
        "user": user,
        "alerts": alerts,
        "max_level": max_level,
        "critical": critical,
        "attention": attention,
        "info": info,
        "min_distance": min_distance,
    }


def build_summary_email(summary: dict[str, Any]) -> tuple[str, str]:
    user = summary["user"]
    alerts = summary["alerts"]
    subject = f"CampoSeguro: alerta {summary['max_level']} · {len(alerts)} zona(s) con riesgo"
    lines = [
        "CampoSeguro — Resumen inteligente de alertas de focos de calor",
        "",
        f"Nivel máximo detectado: {summary['max_level']}",
        f"Zonas con alerta: {len(alerts)}",
        f"Críticas: {summary['critical']} | Atención: {summary['attention']} | Informativas: {summary['info']}",
        f"Distancia mínima: {summary['min_distance']:.2f} km",
        "",
        "Detalle por zona:",
    ]
    for a in alerts:
        google = ""
        if a.get("foco_lat") is not None and a.get("foco_lon") is not None:
            google = f"https://www.google.com/maps?q={a['foco_lat']},{a['foco_lon']}"
        lines.extend(
            [
                "",
                f"- {a['zone_name']} ({a.get('municipio') or a['zone_name']})",
                f"  Nivel: {a['level']}",
                f"  Radio configurado: {float(a.get('radius_km') or 0):.1f} km",
                f"  Focos dentro del radio: {a['foco_count']}",
                f"  Distancia mínima: {float(a['min_distance_km'] or 0):.2f} km",
                f"  Fuente: {a.get('source') or 'FIRMS'}",
                f"  Última detección: {a.get('latest_detection') or ''}",
            ]
        )
        if google:
            lines.append(f"  Mapa: {google}")
    lines.extend(
        [
            "",
            "Recomendación general:",
            "Mantener seguimiento preventivo, revisar reportes locales y validar en campo si corresponde.",
            "",
            "Nota: CampoSeguro es una herramienta informativa. No reemplaza verificación en campo ni sistemas oficiales de emergencia.",
            f"Portal: {config.PUBLIC_BASE_URL}",
        ]
    )
    return subject, "\n".join(lines)


def queue_summary_emails() -> int:
    rows = db.execute(
        """
        SELECT DISTINCT u.id
        FROM users u
        JOIN zone_alerts a ON a.user_id=u.id
        WHERE u.active=TRUE AND u.role='client' AND a.active=TRUE
        ORDER BY u.id
        """,
        fetch="all",
    ) or []
    queued = 0
    today = local_date_str()
    for row in rows:
        summary = user_alert_summary(row["id"])
        if not summary:
            continue
        if len(summary["alerts"]) < config.EMAIL_SUMMARY_MIN_ALERT_ZONES:
            continue
        subject, body = build_summary_email(summary)
        dedupe = f"daily:{row['id']}:{today}"
        user = summary["user"]
        if emailer.queue_email(user["id"], user["email"], "daily_summary", subject, body, dedupe):
            queued += 1
    return queued


def queue_urgent_emails() -> int:
    if not config.EMAIL_URGENT_ENABLED:
        return 0
    rows = db.execute(
        """
        SELECT a.*, u.email, u.name AS user_name, z.name AS zone_name, z.municipio, z.radius_km, f.lat AS foco_lat, f.lon AS foco_lon, f.source
        FROM zone_alerts a
        JOIN users u ON u.id=a.user_id
        JOIN zones z ON z.id=a.zone_id
        LEFT JOIN focos f ON f.id=a.nearest_foco_id
        WHERE a.active=TRUE AND a.level='CRITICO' AND u.active=TRUE
        ORDER BY a.min_distance_km ASC
        """,
        fetch="all",
    ) or []
    queued = 0
    for a in rows:
        recent = db.execute(
            """
            SELECT COUNT(*) AS n
            FROM email_outbox
            WHERE user_id=%s AND kind='urgent' AND dedupe_key LIKE %s
              AND created_at > now() - (%s || ' hours')::interval
            """,
            (a["user_id"], f"urgent:{a['user_id']}:{a['zone_id']}:%", str(config.EMAIL_URGENT_COOLDOWN_HOURS)),
            fetch="one",
        )
        if int(recent["n"]) > 0:
            continue
        subject = f"CampoSeguro: URGENTE CRÍTICO en {a['zone_name']}"
        google = ""
        if a.get("foco_lat") is not None and a.get("foco_lon") is not None:
            google = f"https://www.google.com/maps?q={a['foco_lat']},{a['foco_lon']}"
        body = (
            "CampoSeguro detectó una alerta CRÍTICA dentro de una zona monitoreada.\n\n"
            f"Zona: {a['zone_name']}\n"
            f"Municipio: {a.get('municipio') or a['zone_name']}\n"
            f"Radio configurado: {float(a.get('radius_km') or 0):.1f} km\n"
            f"Focos dentro del radio: {a['foco_count']}\n"
            f"Distancia mínima: {float(a['min_distance_km'] or 0):.2f} km\n"
            f"Fuente: {a.get('source') or 'FIRMS'}\n"
            f"Mapa: {google}\n\n"
            "Recomendación: verificar de forma prioritaria, comunicar a responsables locales y revisar condiciones de propagación.\n\n"
            "Nota: CampoSeguro es informativo y no reemplaza sistemas oficiales de emergencia."
        )
        dedupe = f"urgent:{a['user_id']}:{a['zone_id']}:{int(time.time() // (config.EMAIL_URGENT_COOLDOWN_HOURS * 3600))}"
        if emailer.queue_email(a["user_id"], a["email"], "urgent", subject, body, dedupe):
            queued += 1
    return queued


def run_monitor(trigger: str = "manual") -> dict[str, Any]:
    if db.get_state("running", "false") == "true":
        return {"status": "already_running"}
    db.set_state("running", "true")
    db.set_state("last_trigger", trigger)
    db.set_state("status", "Ejecutando")
    db.set_state("last_error", "")
    result: dict[str, Any] = {}
    try:
        rows, errors = fetch_all_firms()
        new_focos = save_focos(rows)
        alert_zones = recalc_alerts()
        daily_queued = queue_summary_emails()
        urgent_queued = queue_urgent_emails()
        email_result = emailer.process_outbox()
        result = {
            "status": "ok",
            "downloaded": len(rows),
            "new_focos": new_focos,
            "alert_zones": alert_zones,
            "daily_queued": daily_queued,
            "urgent_queued": urgent_queued,
            "email_processed": email_result.get("processed", 0),
            "email_sent": email_result.get("sent", 0),
            "email_errors": email_result.get("errors", 0),
            "errors": errors,
        }
        db.set_state("status", "Correcto")
        db.set_state("last_run_utc", now_utc().isoformat())
        db.set_state("last_downloaded", len(rows))
        db.set_state("last_new_focos", new_focos)
        db.set_state("last_alert_zones", alert_zones)
        db.set_state("last_daily_queued", daily_queued)
        db.set_state("last_urgent_queued", urgent_queued)
        db.set_state("last_email_sent", email_result.get("sent", 0))
        db.set_state("last_email_errors", email_result.get("errors", 0))
        db.set_state("last_fetch_errors", " | ".join(errors)[:1000])
        return result
    except Exception as exc:
        db.set_state("status", "Error")
        db.set_state("last_error", repr(exc))
        raise
    finally:
        db.set_state("running", "false")
