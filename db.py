from __future__ import annotations

import hashlib
import secrets
from contextlib import contextmanager
from typing import Any, Iterable

import psycopg2
import psycopg2.extras

import config


class DatabaseNotConfigured(RuntimeError):
    pass


def password_hash(password: str) -> str:
    salt = config.SESSION_SECRET
    return hashlib.sha256((salt + "::" + (password or "")).encode("utf-8")).hexdigest()


def check_password(password: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False
    return secrets.compare_digest(password_hash(password), stored_hash)


@contextmanager
def get_conn():
    if not config.DATABASE_URL:
        raise DatabaseNotConfigured("DATABASE_URL no está configurada. Usa PostgreSQL para CampoSeguro v4.1.")
    conn = psycopg2.connect(config.DATABASE_URL, sslmode="require")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute(sql: str, params: tuple | list | None = None, fetch: str | None = None) -> Any:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or ())
            if fetch == "one":
                return cur.fetchone()
            if fetch == "all":
                return cur.fetchall()
            if fetch == "value":
                row = cur.fetchone()
                if not row:
                    return None
                return next(iter(row.values()))
            return cur.rowcount


def executemany(sql: str, rows: Iterable[tuple]) -> int:
    count = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(sql, row)
                count += cur.rowcount
    return count


def init_db() -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            organization TEXT DEFAULT '',
            email TEXT UNIQUE NOT NULL,
            phone TEXT DEFAULT '',
            role TEXT NOT NULL DEFAULT 'client',
            password_hash TEXT DEFAULT '',
            client_token TEXT UNIQUE NOT NULL,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS zones (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            municipio TEXT DEFAULT '',
            lat DOUBLE PRECISION NOT NULL,
            lon DOUBLE PRECISION NOT NULL,
            radius_km DOUBLE PRECISION NOT NULL DEFAULT 15,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS focos (
            id SERIAL PRIMARY KEY,
            external_id TEXT UNIQUE NOT NULL,
            source TEXT NOT NULL,
            lat DOUBLE PRECISION NOT NULL,
            lon DOUBLE PRECISION NOT NULL,
            acq_date TEXT DEFAULT '',
            acq_time TEXT DEFAULT '',
            satellite TEXT DEFAULT '',
            confidence TEXT DEFAULT '',
            frp TEXT DEFAULT '',
            daynight TEXT DEFAULT '',
            raw JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS zone_alerts (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            zone_id INTEGER NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
            level TEXT NOT NULL,
            foco_count INTEGER NOT NULL DEFAULT 0,
            nearest_foco_id INTEGER REFERENCES focos(id) ON DELETE SET NULL,
            min_distance_km DOUBLE PRECISION,
            latest_detection TEXT DEFAULT '',
            message TEXT DEFAULT '',
            active BOOLEAN NOT NULL DEFAULT TRUE,
            calculated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(zone_id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS email_outbox (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            recipient TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'summary',
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            dedupe_key TEXT UNIQUE,
            status TEXT NOT NULL DEFAULT 'queued',
            provider TEXT DEFAULT '',
            provider_response TEXT DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            processed_at TIMESTAMPTZ
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS monitor_state (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT '',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """,

        # Migraciones suaves para repositorios que ya tenían tablas anteriores.
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS organization TEXT DEFAULT '';",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT DEFAULT '';",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'client';",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT DEFAULT '';",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS client_token TEXT;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE;",
        "UPDATE users SET client_token = substr(md5(random()::text || clock_timestamp()::text),1,24) WHERE client_token IS NULL OR client_token='';",
        "ALTER TABLE users ALTER COLUMN client_token SET NOT NULL;",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_client_token_unique ON users(client_token);",
        "ALTER TABLE zones ADD COLUMN IF NOT EXISTS user_id INTEGER;",
        "ALTER TABLE zones ADD COLUMN IF NOT EXISTS municipio TEXT DEFAULT '';",
        "ALTER TABLE zones ADD COLUMN IF NOT EXISTS radius_km DOUBLE PRECISION NOT NULL DEFAULT 15;",
        "ALTER TABLE zones ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE;",
        "ALTER TABLE focos ADD COLUMN IF NOT EXISTS external_id TEXT;",
        "ALTER TABLE focos ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'FIRMS';",
        "ALTER TABLE focos ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION;",
        "ALTER TABLE focos ADD COLUMN IF NOT EXISTS lon DOUBLE PRECISION;",
        "ALTER TABLE focos ADD COLUMN IF NOT EXISTS acq_date TEXT DEFAULT '';",
        "ALTER TABLE focos ADD COLUMN IF NOT EXISTS acq_time TEXT DEFAULT '';",
        "ALTER TABLE focos ADD COLUMN IF NOT EXISTS satellite TEXT DEFAULT '';",
        "ALTER TABLE focos ADD COLUMN IF NOT EXISTS confidence TEXT DEFAULT '';",
        "ALTER TABLE focos ADD COLUMN IF NOT EXISTS frp TEXT DEFAULT '';",
        "ALTER TABLE focos ADD COLUMN IF NOT EXISTS daynight TEXT DEFAULT '';",
        "ALTER TABLE zone_alerts ADD COLUMN IF NOT EXISTS user_id INTEGER;",
        "ALTER TABLE zone_alerts ADD COLUMN IF NOT EXISTS zone_id INTEGER;",
        "ALTER TABLE zone_alerts ADD COLUMN IF NOT EXISTS level TEXT DEFAULT 'INFORMATIVO';",
        "ALTER TABLE zone_alerts ADD COLUMN IF NOT EXISTS foco_count INTEGER NOT NULL DEFAULT 0;",
        "ALTER TABLE zone_alerts ADD COLUMN IF NOT EXISTS nearest_foco_id INTEGER;",
        "ALTER TABLE zone_alerts ADD COLUMN IF NOT EXISTS min_distance_km DOUBLE PRECISION;",
        "ALTER TABLE zone_alerts ADD COLUMN IF NOT EXISTS latest_detection TEXT DEFAULT '';",
        "ALTER TABLE zone_alerts ADD COLUMN IF NOT EXISTS message TEXT DEFAULT '';",
        "ALTER TABLE zone_alerts ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE;",
        "DELETE FROM zone_alerts a USING zone_alerts b WHERE a.zone_id=b.zone_id AND a.id<b.id;",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_zone_alerts_zone_unique ON zone_alerts(zone_id);",
        "CREATE INDEX IF NOT EXISTS idx_zones_user ON zones(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_focos_lat_lon ON focos(lat, lon);",
        "CREATE INDEX IF NOT EXISTS idx_focos_source ON focos(source);",
        "CREATE INDEX IF NOT EXISTS idx_alerts_user ON zone_alerts(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_email_status ON email_outbox(status);",
        "CREATE INDEX IF NOT EXISTS idx_email_user_kind ON email_outbox(user_id, kind);",
    ]
    with get_conn() as conn:
        with conn.cursor() as cur:
            for stmt in statements:
                cur.execute(stmt)


def set_state(key: str, value: Any) -> None:
    execute(
        """
        INSERT INTO monitor_state(key, value, updated_at)
        VALUES (%s, %s, now())
        ON CONFLICT(key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """,
        (key, str(value)),
    )


def get_state(key: str, default: str = "") -> str:
    row = execute("SELECT value FROM monitor_state WHERE key=%s", (key,), fetch="one")
    return str(row["value"]) if row else default


def all_state() -> dict[str, str]:
    rows = execute("SELECT key, value FROM monitor_state ORDER BY key", fetch="all") or []
    return {r["key"]: r["value"] for r in rows}


def seed_data() -> None:
    admin = execute("SELECT id FROM users WHERE email=%s", (config.ADMIN_EMAIL,), fetch="one")
    if not admin:
        execute(
            """
            INSERT INTO users(name, organization, email, phone, role, password_hash, client_token)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                "Administrador CampoSeguro",
                "CampoSeguro",
                config.ADMIN_EMAIL,
                "",
                "admin",
                password_hash(config.ADMIN_PASSWORD),
                secrets.token_urlsafe(24),
            ),
        )
    else:
        execute(
            "UPDATE users SET role='admin', password_hash=%s WHERE email=%s",
            (password_hash(config.ADMIN_PASSWORD), config.ADMIN_EMAIL),
        )

    client = execute("SELECT id FROM users WHERE email=%s", (config.CLIENT_DEMO_EMAIL,), fetch="one")
    if not client:
        client = execute(
            """
            INSERT INTO users(name, organization, email, phone, role, password_hash, client_token)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                "Usuario piloto",
                "CampoSeguro",
                config.CLIENT_DEMO_EMAIL,
                config.CLIENT_DEMO_PHONE,
                "client",
                password_hash(config.CLIENT_DEMO_PASSWORD),
                secrets.token_urlsafe(24),
            ),
            fetch="one",
        )
    client_id = client["id"]
    existing_zones = execute("SELECT COUNT(*) AS n FROM zones WHERE user_id=%s", (client_id,), fetch="one")
    if int(existing_zones["n"]) == 0:
        seed_zones = [
            (client_id, "Santa Cruz de la Sierra", "Santa Cruz de la Sierra", -17.7833, -63.1821, config.DEFAULT_ZONE_RADIUS_KM),
            (client_id, "San Ignacio de Velasco", "San Ignacio de Velasco", -16.3667, -60.9500, config.DEFAULT_ZONE_RADIUS_KM),
            (client_id, "Roboré", "Roboré", -18.3333, -59.7500, config.DEFAULT_ZONE_RADIUS_KM),
            (client_id, "San Matías", "San Matías", -16.3667, -58.4000, config.DEFAULT_ZONE_RADIUS_KM),
            (client_id, "Puerto Suárez", "Puerto Suárez", -18.9500, -57.8000, config.DEFAULT_ZONE_RADIUS_KM),
            (client_id, "Charagua Iyambae", "Charagua Iyambae", -19.8000, -63.2000, config.DEFAULT_ZONE_RADIUS_KM),
        ]
        executemany(
            "INSERT INTO zones(user_id, name, municipio, lat, lon, radius_km) VALUES (%s,%s,%s,%s,%s,%s)",
            seed_zones,
        )

    for key, val in {
        "running": "false",
        "status": "Inicializado",
        "last_error": "",
        "app_version": config.APP_VERSION,
    }.items():
        if not get_state(key):
            set_state(key, val)
