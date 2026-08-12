"""Worker independiente para Render.

Uso recomendado en producción:
  - Web service: uvicorn app:app --host 0.0.0.0 --port $PORT
  - Background worker: python auto_monitor.py

En el web service puedes dejar AUTO_MONITOR_ENABLED=false para evitar doble ejecución.
"""

import time

import config
import db
import monitor


def main() -> None:
    db.init_db()
    db.seed_data()
    db.set_state("worker_status", "Activo")
    while True:
        try:
            monitor.run_monitor("background-worker")
        except Exception as exc:
            db.set_state("worker_status", "Error")
            db.set_state("last_error", repr(exc))
        time.sleep(max(60, config.MONITOR_INTERVAL_MINUTES * 60))


if __name__ == "__main__":
    main()
