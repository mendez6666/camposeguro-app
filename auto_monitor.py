import json
import threading
import time
import traceback
from datetime import datetime, timezone

from config import (
    AUTO_MONITOR_ENABLED,
    AUTO_MONITOR_INTERVAL_MINUTES,
    AUTO_MONITOR_RUN_ON_STARTUP,
    AUTO_MONITOR_START_DELAY_SECONDS,
    MONITOR_STATUS_PATH,
)
from monitor import run_monitoring
from emailer import preparar_correos_pendientes, procesar_correos_pendientes, smtp_config_ok


_lock = threading.Lock()
_thread_started = False
_last_status = {
    "running": False,
    "enabled": AUTO_MONITOR_ENABLED,
    "last_run_utc": None,
    "last_success": None,
    "last_error": None,
    "last_trigger": None,
    "next_run_hint": None,
    "runs": 0,
}


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def _save_status(status):
    try:
        MONITOR_STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _load_status():
    try:
        if MONITOR_STATUS_PATH.exists():
            data = json.loads(MONITOR_STATUS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _last_status.update(data)
    except Exception:
        pass


def get_auto_monitor_status():
    _load_status()
    status = dict(_last_status)
    status["enabled"] = AUTO_MONITOR_ENABLED
    status["interval_minutes"] = AUTO_MONITOR_INTERVAL_MINUTES
    status["run_on_startup"] = AUTO_MONITOR_RUN_ON_STARTUP
    status["smtp_active"] = smtp_config_ok()
    return status


def run_monitor_once(trigger="manual"):
    """
    Ejecuta monitoreo completo:
    1. FIRMS
    2. Guarda focos
    3. Recalcula alertas
    4. Prepara correos
    5. Procesa correos: si SMTP está activo envía; si no, genera outbox
    """
    if not _lock.acquire(blocking=False):
        status = get_auto_monitor_status()
        status["message"] = "El monitoreo ya está en ejecución."
        return status

    try:
        _last_status.update({
            "running": True,
            "last_trigger": trigger,
            "last_start_utc": now_utc(),
            "last_error": None,
        })
        _save_status(_last_status)

        result = run_monitoring()
        correos_preparados = preparar_correos_pendientes()
        correos_procesados = procesar_correos_pendientes()

        _last_status.update({
            "running": False,
            "last_run_utc": now_utc(),
            "last_success": True,
            "last_error": None,
            "last_trigger": trigger,
            "runs": int(_last_status.get("runs") or 0) + 1,
            "last_result": result,
            "correos_preparados": correos_preparados,
            "correos_procesados": correos_procesados,
            "next_run_hint": f"aprox. en {AUTO_MONITOR_INTERVAL_MINUTES} minutos si el servicio sigue despierto",
        })
        _save_status(_last_status)
        return dict(_last_status)

    except Exception as exc:
        _last_status.update({
            "running": False,
            "last_run_utc": now_utc(),
            "last_success": False,
            "last_error": str(exc),
            "last_traceback": traceback.format_exc(),
            "last_trigger": trigger,
        })
        _save_status(_last_status)
        return dict(_last_status)

    finally:
        _lock.release()


def _loop():
    if AUTO_MONITOR_RUN_ON_STARTUP:
        time.sleep(max(1, AUTO_MONITOR_START_DELAY_SECONDS))
        run_monitor_once(trigger="startup")

    while True:
        time.sleep(max(15, AUTO_MONITOR_INTERVAL_MINUTES * 60))
        run_monitor_once(trigger="auto_interval")


def start_background_monitor():
    global _thread_started

    if not AUTO_MONITOR_ENABLED:
        return False

    if _thread_started:
        return True

    t = threading.Thread(target=_loop, name="camposeguro-auto-monitor", daemon=True)
    t.start()
    _thread_started = True
    return True
