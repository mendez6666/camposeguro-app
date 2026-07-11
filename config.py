from pathlib import Path
import os
import re
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

DB_PATH = ROOT_DIR / "camposeguro.db"
OUTPUT_DIR = ROOT_DIR / "output"
OUTBOX_DIR = OUTPUT_DIR / "outbox_email"

RAW_FIRMS_MAP_KEY = os.getenv("FIRMS_MAP_KEY", "").strip()


def normalize_map_key(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""

    m = re.search(r"South_America/([a-fA-F0-9]{32})", raw)
    if m:
        return m.group(1)

    m = re.search(r"\b([a-fA-F0-9]{32})\b", raw)
    if m:
        return m.group(1)

    return raw


FIRMS_MAP_KEY = normalize_map_key(RAW_FIRMS_MAP_KEY)
FIRMS_AREA_BBOX = os.getenv("FIRMS_AREA_BBOX", "-64.9,-20.6,-57.0,-13.0").strip()
FIRMS_DAY_RANGE = int(os.getenv("FIRMS_DAY_RANGE", "1"))
FIRMS_SOURCES = [
    x.strip() for x in os.getenv(
        "FIRMS_SOURCES",
        "MODIS_NRT,VIIRS_SNPP_NRT,VIIRS_NOAA20_NRT,VIIRS_NOAA21_NRT"
    ).split(",")
    if x.strip()
]

# Correo / SMTP
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").strip().lower() in ["1", "true", "yes", "si", "sí"]
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").strip().lower() in ["1", "true", "yes", "si", "sí"]
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER).strip()
