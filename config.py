import os
import re
from dotenv import load_dotenv

load_dotenv()

APP_NAME = "CampoSeguro"
APP_VERSION = "4.1"


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, str(default))).strip())
    except Exception:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(str(os.getenv(name, str(default))).strip())
    except Exception:
        return default


def normalize_firms_key(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    match = re.search(r"South_America/([a-fA-F0-9]{32})", raw)
    if match:
        return match.group(1)
    match = re.search(r"([a-fA-F0-9]{32})", raw)
    if match:
        return match.group(1)
    return raw


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SESSION_SECRET = os.getenv("SESSION_SECRET", "cambiar-session-secret-camposeguro")

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@camposeguro.app").strip().lower()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Cambiar123!")

LOGO_CAMPOSEGURO_URL = os.getenv(
    "LOGO_CAMPOSEGURO_URL",
    "https://i.ibb.co/VWnQ8RZY/logo-campo-seguro.png",
).strip()

RAW_FIRMS_MAP_KEY = os.getenv("FIRMS_MAP_KEY", "").strip()
FIRMS_MAP_KEY = normalize_firms_key(RAW_FIRMS_MAP_KEY)
FIRMS_AREA_BBOX = os.getenv("FIRMS_AREA_BBOX", "-70.0,-23.5,-57.0,-9.0").strip()
FIRMS_SOURCES = [s.strip() for s in os.getenv(
    "FIRMS_SOURCES",
    "MODIS_NRT,VIIRS_SNPP_NRT,VIIRS_NOAA20_NRT,VIIRS_NOAA21_NRT",
).split(",") if s.strip()]
FIRMS_DAY_RANGE = env_int("FIRMS_DAY_RANGE", 5)
FIRMS_REQUEST_TIMEOUT_SECONDS = env_int("FIRMS_REQUEST_TIMEOUT_SECONDS", 30)

DEFAULT_ZONE_RADIUS_KM = env_float("DEFAULT_ZONE_RADIUS_KM", 15.0)
ALERT_CRITICAL_KM = env_float("ALERT_CRITICAL_KM", 10.0)
ALERT_ATTENTION_KM = env_float("ALERT_ATTENTION_KM", 25.0)

MONITOR_INTERVAL_MINUTES = env_int("MONITOR_INTERVAL_MINUTES", 180)
AUTO_MONITOR_ENABLED = env_bool("AUTO_MONITOR_ENABLED", True)

EMAIL_ENABLED = env_bool("EMAIL_ENABLED", True)
EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "resend_api").strip().lower()
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
EMAIL_FROM = os.getenv("EMAIL_FROM", "CampoSeguro <alertas@camposeguro.app>").strip()
EMAIL_REPLY_TO = os.getenv("EMAIL_REPLY_TO", "").strip()
EMAIL_TIMEZONE_OFFSET_HOURS = env_int("EMAIL_TIMEZONE_OFFSET_HOURS", -4)
EMAIL_DAILY_MAX_PER_RECIPIENT = env_int("EMAIL_DAILY_MAX_PER_RECIPIENT", 1)
EMAIL_SUMMARY_MIN_ALERT_ZONES = env_int("EMAIL_SUMMARY_MIN_ALERT_ZONES", 1)
EMAIL_SUMMARY_HOUR_LOCAL = env_int("EMAIL_SUMMARY_HOUR_LOCAL", 7)
EMAIL_URGENT_ENABLED = env_bool("EMAIL_URGENT_ENABLED", True)
EMAIL_URGENT_MIN_LEVEL = os.getenv("EMAIL_URGENT_MIN_LEVEL", "CRITICO").strip().upper()
EMAIL_URGENT_COOLDOWN_HOURS = env_int("EMAIL_URGENT_COOLDOWN_HOURS", 12)
EMAIL_PROCESS_MAX_PER_RUN = env_int("EMAIL_PROCESS_MAX_PER_RUN", 50)
EMAIL_API_TIMEOUT_SECONDS = env_int("EMAIL_API_TIMEOUT_SECONDS", 18)

CLIENT_DEMO_EMAIL = os.getenv("CLIENT_DEMO_EMAIL", "cliente@camposeguro.app").strip().lower()
CLIENT_DEMO_PASSWORD = os.getenv("CLIENT_DEMO_PASSWORD", "demo123")
CLIENT_DEMO_PHONE = os.getenv("CLIENT_DEMO_PHONE", "+59178061775").strip()

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://app.camposeguro.app").rstrip("/")
