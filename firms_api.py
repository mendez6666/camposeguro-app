import csv
from io import StringIO
import requests
from config import FIRMS_MAP_KEY, FIRMS_AREA_BBOX, FIRMS_DAY_RANGE, FIRMS_SOURCES


AREA_PRESETS = {
    "Santa Cruz": "-64.9,-20.6,-57.0,-13.0",
    "Bolivia": "-70.0,-23.5,-57.0,-9.0",
}

API_REGION_LABEL = "South_America"


def mask_key_in_url(url: str) -> str:
    if not FIRMS_MAP_KEY:
        return url
    return url.replace(FIRMS_MAP_KEY, f"{FIRMS_MAP_KEY[:6]}...{FIRMS_MAP_KEY[-4:]}")


def masked_key():
    if not FIRMS_MAP_KEY:
        return "VACÍA"
    if len(FIRMS_MAP_KEY) <= 10:
        return FIRMS_MAP_KEY[:3] + "..."
    return f"{FIRMS_MAP_KEY[:6]}...{FIRMS_MAP_KEY[-4:]} ({len(FIRMS_MAP_KEY)} caracteres)"


def check_key():
    if not FIRMS_MAP_KEY or FIRMS_MAP_KEY in ["coloca_aqui_tu_map_key", "tu_llave_FIRMS", "TU_LLAVE_REAL"]:
        raise RuntimeError("Falta configurar FIRMS_MAP_KEY en Render Environment Variables.")


def build_area_url(source, bbox=None, days=None):
    check_key()
    bbox = bbox or FIRMS_AREA_BBOX
    days = int(days or FIRMS_DAY_RANGE)
    return f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_MAP_KEY}/{source}/{bbox}/{days}"


def parse_firms_csv(text, source):
    text = (text or "").strip()
    if not text:
        return [], ""

    first = text.splitlines()[0].lower()
    if "latitude" not in first or "longitude" not in first:
        return [], text[:2000]

    reader = csv.DictReader(StringIO(text))
    rows = []
    parse_errors = 0
    for row in reader:
        try:
            rows.append({
                "fuente": source,
                "latitude": float(row.get("latitude", "")),
                "longitude": float(row.get("longitude", "")),
                "acq_date": row.get("acq_date", ""),
                "acq_time": row.get("acq_time", ""),
                "satellite": row.get("satellite", ""),
                "instrument": row.get("instrument", ""),
                "confidence": row.get("confidence", ""),
                "frp": row.get("frp", ""),
                "bright_ti4": row.get("bright_ti4", row.get("brightness", "")),
                "daynight": row.get("daynight", ""),
            })
        except Exception:
            parse_errors += 1
            continue
    msg = f"Filas no parseadas: {parse_errors}" if parse_errors else ""
    return rows, msg


def fetch_source(source):
    url = build_area_url(source)
    r = requests.get(url, timeout=90)
    r.raise_for_status()
    rows, msg = parse_firms_csv(r.text, source)
    return rows, msg


def test_source(source, bbox=None, days=None):
    """
    Prueba técnica para Render: no guarda nada en la base.
    Devuelve URL enmascarada, status, primeras líneas y cantidad parseada.
    """
    try:
        url = build_area_url(source, bbox=bbox, days=days)
        r = requests.get(url, timeout=90)
        text = r.text or ""
        first_lines = "\n".join(text.splitlines()[:8])
        parsed_rows, parse_msg = parse_firms_csv(text, source)

        return {
            "source": source,
            "url": mask_key_in_url(url),
            "status_code": r.status_code,
            "ok": r.ok,
            "parsed_count": len(parsed_rows),
            "first_lines": first_lines[:2500],
            "error": "" if r.ok else f"HTTP {r.status_code}: {text[:800]}",
            "parse_message": parse_msg,
        }
    except Exception as exc:
        try:
            masked_url = mask_key_in_url(build_area_url(source, bbox=bbox, days=days))
        except Exception:
            masked_url = "No se pudo construir URL"
        return {
            "source": source,
            "url": masked_url,
            "status_code": "",
            "ok": False,
            "parsed_count": 0,
            "first_lines": "",
            "error": str(exc),
            "parse_message": "",
        }


def fetch_all_sources(bbox=None, days=None, area_name=None):
    all_rows = []
    reports = []
    seen = set()

    for source in FIRMS_SOURCES:
        try:
            url = build_area_url(source, bbox=bbox, days=days)
            r = requests.get(url, timeout=90)
            r.raise_for_status()
            rows, msg = parse_firms_csv(r.text, source)
            added = 0
            for row in rows:
                key = (row["fuente"], row["latitude"], row["longitude"], row["acq_date"], row["acq_time"])
                if key not in seen:
                    seen.add(key)
                    all_rows.append(row)
                    added += 1
            reports.append({
                "source": source,
                "area": area_name or "Personalizada",
                "bbox": bbox or FIRMS_AREA_BBOX,
                "count": len(rows),
                "added": added,
                "message": msg,
                "error": "",
                "url": mask_key_in_url(url),
            })
        except Exception as exc:
            url = ""
            try:
                url = mask_key_in_url(build_area_url(source, bbox=bbox, days=days))
            except Exception:
                pass
            reports.append({
                "source": source,
                "area": area_name or "Personalizada",
                "bbox": bbox or FIRMS_AREA_BBOX,
                "count": 0,
                "added": 0,
                "message": "",
                "error": str(exc),
                "url": url,
            })

    return all_rows, reports


def fetch_auto_scz_bolivia(days=None):
    """
    Estrategia CampoSeguro:
    1) Consulta Santa Cruz.
    2) Si todas las fuentes devuelven 0 filas, consulta Bolivia.
    No consulta toda Sudamérica para evitar ruido y exceso de datos.
    """
    all_reports = []
    strategy = []
    days = int(days or FIRMS_DAY_RANGE)

    for area_name in ["Santa Cruz", "Bolivia"]:
        bbox = AREA_PRESETS[area_name]
        rows, reports = fetch_all_sources(bbox=bbox, days=days, area_name=area_name)
        total = len(rows)
        strategy.append({"area": area_name, "bbox": bbox, "rows": total, "days": days})
        all_reports.extend(reports)

        if total > 0:
            return rows, all_reports, {
                "api_region": API_REGION_LABEL,
                "selected_area": area_name,
                "selected_bbox": bbox,
                "days": days,
                "strategy": strategy,
                "fallback_used": area_name != "Santa Cruz",
            }

    return [], all_reports, {
        "api_region": API_REGION_LABEL,
        "selected_area": "Sin focos detectados en Santa Cruz ni Bolivia",
        "selected_bbox": "",
        "days": days,
        "strategy": strategy,
        "fallback_used": True,
    }
