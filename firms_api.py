import csv
from io import StringIO
import requests
from config import FIRMS_MAP_KEY, FIRMS_AREA_BBOX, FIRMS_DAY_RANGE, FIRMS_SOURCES


def check_key():
    if not FIRMS_MAP_KEY or FIRMS_MAP_KEY == "coloca_aqui_tu_map_key":
        raise RuntimeError("Falta configurar FIRMS_MAP_KEY en .env")


def fetch_source(source):
    check_key()
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_MAP_KEY}/{source}/{FIRMS_AREA_BBOX}/{FIRMS_DAY_RANGE}"
    r = requests.get(url, timeout=90)
    r.raise_for_status()
    text = r.text.strip()

    if not text:
        return [], ""

    first = text.splitlines()[0].lower()
    if "latitude" not in first or "longitude" not in first:
        return [], text[:1000]

    reader = csv.DictReader(StringIO(text))
    rows = []
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
            continue
    return rows, ""


def fetch_all_sources():
    all_rows = []
    reports = []
    seen = set()

    for source in FIRMS_SOURCES:
        try:
            rows, msg = fetch_source(source)
            added = 0
            for r in rows:
                key = (r["fuente"], r["latitude"], r["longitude"], r["acq_date"], r["acq_time"])
                if key not in seen:
                    seen.add(key)
                    all_rows.append(r)
                    added += 1
            reports.append({"source": source, "count": len(rows), "added": added, "message": msg, "error": ""})
        except Exception as exc:
            reports.append({"source": source, "count": 0, "added": 0, "message": "", "error": str(exc)})

    return all_rows, reports