import math
from datetime import datetime, timezone
from firms_api import fetch_all_sources
from db import get_conn


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def nivel_alerta(distancia_km):
    if distancia_km <= 10:
        return "CRITICO"
    if distancia_km <= 25:
        return "ATENCION"
    return "INFORMATIVO"


def insert_foco(conn, f):
    external_key = f'{f["fuente"]}_{f["latitude"]}_{f["longitude"]}_{f["acq_date"]}_{f["acq_time"]}'
    conn.execute("""
        INSERT OR IGNORE INTO focos
        (external_key, fuente, latitude, longitude, acq_date, acq_time, satellite, instrument, confidence, frp, bright_ti4, daynight, creado_utc)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        external_key, f["fuente"], f["latitude"], f["longitude"], f["acq_date"], f["acq_time"],
        f["satellite"], f["instrument"], str(f["confidence"]), str(f["frp"]), str(f["bright_ti4"]),
        str(f["daynight"]), now_utc()
    ))
    row = conn.execute("SELECT id FROM focos WHERE external_key = ?", (external_key,)).fetchone()
    return row["id"]


def insert_alerta(conn, zona, foco_id, distancia_km):
    nivel = nivel_alerta(distancia_km)
    alerta_key = f'z{zona["id"]}_f{foco_id}'
    conn.execute("""
        INSERT OR IGNORE INTO alertas
        (alerta_key, zona_id, foco_id, distancia_km, nivel, creada_utc)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (alerta_key, zona["id"], foco_id, round(distancia_km, 2), nivel, now_utc()))


def recalcular_alertas_existentes():
    conn = get_conn()
    conn.execute("DELETE FROM alertas")
    zonas = conn.execute("SELECT * FROM zonas WHERE activa=1").fetchall()
    focos = conn.execute("SELECT * FROM focos").fetchall()
    total = 0

    for foco in focos:
        for zona in zonas:
            dist = haversine_km(zona["latitud"], zona["longitud"], foco["latitude"], foco["longitude"])
            if dist <= float(zona["radio_km"]):
                insert_alerta(conn, zona, foco["id"], dist)
                total += 1

    conn.commit()
    conn.close()
    return total


def run_monitoring():
    focos, reports = fetch_all_sources()

    conn = get_conn()
    fires_before = conn.execute("SELECT COUNT(*) FROM focos").fetchone()[0]

    for f in focos:
        insert_foco(conn, f)

    conn.commit()
    fires_after = conn.execute("SELECT COUNT(*) FROM focos").fetchone()[0]
    conn.close()

    alerts_total = recalcular_alertas_existentes()

    return {
        "focos_descargados": len(focos),
        "focos_nuevos_guardados": fires_after - fires_before,
        "alertas_totales": alerts_total,
        "reports": reports,
        "fecha_utc": now_utc()
    }


def clear_data():
    conn = get_conn()
    conn.execute("DELETE FROM alertas")
    conn.execute("DELETE FROM focos")
    conn.commit()
    conn.close()