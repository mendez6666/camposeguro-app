import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from config import DB_PATH, DATABASE_URL, DB_BACKEND, DEFAULT_ZONE_RADIUS_KM


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def is_postgres():
    return DB_BACKEND == "postgresql"


class DBRow(dict):
    """Fila compatible con acceso por nombre y por índice."""
    def __init__(self, data=None, order=None):
        super().__init__(data or {})
        self._order = list(order or self.keys())

    def __getitem__(self, key):
        if isinstance(key, int):
            if key < 0:
                key = len(self._order) + key
            return dict.__getitem__(self, self._order[key])
        return dict.__getitem__(self, key)


class Result:
    def __init__(self, cursor, provider: str):
        self.cursor = cursor
        self.provider = provider
        self.rowcount = getattr(cursor, "rowcount", -1)

    def _wrap(self, row):
        if row is None:
            return None
        if isinstance(row, DBRow):
            return row
        if self.provider == "postgresql":
            # RealDictCursor devuelve dict preservando orden de columnas.
            return DBRow(dict(row), list(row.keys()))
        # sqlite3.Row
        keys = row.keys()
        return DBRow({k: row[k] for k in keys}, list(keys))

    def fetchone(self):
        return self._wrap(self.cursor.fetchone())

    def fetchall(self):
        return [self._wrap(r) for r in self.cursor.fetchall()]


class DBConnection:
    def __init__(self, raw, provider: str):
        self.raw = raw
        self.provider = provider

    def cursor(self):
        return self

    def _convert_sql(self, sql: str) -> str:
        if self.provider != "postgresql":
            return sql

        s = sql
        stripped = s.lstrip()
        prefix_ws = s[:len(s) - len(stripped)]
        upper = stripped.upper()

        # SQLite compatibility
        if upper.startswith("INSERT OR IGNORE INTO"):
            stripped = stripped.replace("INSERT OR IGNORE INTO", "INSERT INTO", 1)
            s = prefix_ws + stripped
            # ON CONFLICT DO NOTHING funciona si existe UNIQUE/PK conflict.
            if "ON CONFLICT" not in s.upper():
                s = s.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"

        # Placeholders
        s = s.replace("?", "%s")

        return s

    def execute(self, sql: str, params: Optional[Iterable[Any]] = None):
        if params is None:
            params = ()
        if self.provider == "postgresql":
            cur = self.raw.cursor()
            cur.execute(self._convert_sql(sql), tuple(params))
            return Result(cur, self.provider)
        cur = self.raw.execute(sql, tuple(params))
        return Result(cur, self.provider)

    def executemany(self, sql: str, seq_of_params: Iterable[Iterable[Any]]):
        if self.provider == "postgresql":
            cur = self.raw.cursor()
            cur.executemany(self._convert_sql(sql), [tuple(p) for p in seq_of_params])
            return Result(cur, self.provider)
        cur = self.raw.executemany(sql, [tuple(p) for p in seq_of_params])
        return Result(cur, self.provider)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()


def get_conn():
    if is_postgres():
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except Exception as exc:
            raise RuntimeError(
                "Falta psycopg2-binary. Verifica requirements.txt y vuelve a desplegar en Render."
            ) from exc

        url = DATABASE_URL
        # Compatibilidad con urls tipo postgres://
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        raw = psycopg2.connect(url, cursor_factory=RealDictCursor, connect_timeout=10)
        return DBConnection(raw, "postgresql")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return DBConnection(conn, "sqlite")


def _has_column(conn, table, column):
    if is_postgres():
        row = conn.execute("""
            SELECT COUNT(*) AS n
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s AND column_name=%s
        """, (table, column)).fetchone()
        return bool(row and row["n"])

    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return column in [r[1] for r in rows]


def _create_tables_sqlite(conn):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        email TEXT,
        telefono TEXT,
        organizacion TEXT,
        tipo_usuario TEXT,
        activo INTEGER DEFAULT 1,
        creado_utc TEXT NOT NULL
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS zonas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER,
        nombre_zona TEXT NOT NULL,
        contacto_email TEXT,
        tipo_zona TEXT,
        departamento TEXT,
        municipio TEXT,
        latitud REAL NOT NULL,
        longitud REAL NOT NULL,
        radio_km REAL NOT NULL,
        activa INTEGER DEFAULT 1,
        creada_utc TEXT NOT NULL,
        FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS focos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        external_key TEXT UNIQUE,
        fuente TEXT,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        acq_date TEXT,
        acq_time TEXT,
        satellite TEXT,
        instrument TEXT,
        confidence TEXT,
        frp TEXT,
        bright_ti4 TEXT,
        daynight TEXT,
        creado_utc TEXT NOT NULL
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS alertas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alerta_key TEXT UNIQUE,
        zona_id INTEGER NOT NULL,
        foco_id INTEGER NOT NULL,
        distancia_km REAL NOT NULL,
        nivel TEXT NOT NULL,
        creada_utc TEXT NOT NULL,
        FOREIGN KEY(zona_id) REFERENCES zonas(id),
        FOREIGN KEY(foco_id) REFERENCES focos(id)
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS correos_alerta (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alerta_id INTEGER NOT NULL,
        destinatario TEXT NOT NULL,
        asunto TEXT NOT NULL,
        cuerpo TEXT NOT NULL,
        estado TEXT DEFAULT 'pendiente',
        error TEXT,
        creado_utc TEXT NOT NULL,
        enviado_utc TEXT,
        UNIQUE(alerta_id, destinatario),
        FOREIGN KEY(alerta_id) REFERENCES alertas(id)
    )
    """)


def _create_tables_postgres(conn):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY,
        nombre TEXT NOT NULL,
        email TEXT,
        telefono TEXT,
        organizacion TEXT,
        tipo_usuario TEXT,
        activo INTEGER DEFAULT 1,
        creado_utc TEXT NOT NULL
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS zonas (
        id SERIAL PRIMARY KEY,
        usuario_id INTEGER REFERENCES usuarios(id),
        nombre_zona TEXT NOT NULL,
        contacto_email TEXT,
        tipo_zona TEXT,
        departamento TEXT,
        municipio TEXT,
        latitud DOUBLE PRECISION NOT NULL,
        longitud DOUBLE PRECISION NOT NULL,
        radio_km DOUBLE PRECISION NOT NULL,
        activa INTEGER DEFAULT 1,
        creada_utc TEXT NOT NULL
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS focos (
        id SERIAL PRIMARY KEY,
        external_key TEXT UNIQUE,
        fuente TEXT,
        latitude DOUBLE PRECISION NOT NULL,
        longitude DOUBLE PRECISION NOT NULL,
        acq_date TEXT,
        acq_time TEXT,
        satellite TEXT,
        instrument TEXT,
        confidence TEXT,
        frp TEXT,
        bright_ti4 TEXT,
        daynight TEXT,
        creado_utc TEXT NOT NULL
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS alertas (
        id SERIAL PRIMARY KEY,
        alerta_key TEXT UNIQUE,
        zona_id INTEGER NOT NULL REFERENCES zonas(id),
        foco_id INTEGER NOT NULL REFERENCES focos(id),
        distancia_km DOUBLE PRECISION NOT NULL,
        nivel TEXT NOT NULL,
        creada_utc TEXT NOT NULL
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS correos_alerta (
        id SERIAL PRIMARY KEY,
        alerta_id INTEGER NOT NULL REFERENCES alertas(id),
        destinatario TEXT NOT NULL,
        asunto TEXT NOT NULL,
        cuerpo TEXT NOT NULL,
        estado TEXT DEFAULT 'pendiente',
        error TEXT,
        creado_utc TEXT NOT NULL,
        enviado_utc TEXT,
        UNIQUE(alerta_id, destinatario)
    )
    """)

    # Índices útiles para monitoreo.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_focos_fecha ON focos(acq_date, acq_time)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_focos_geo ON focos(latitude, longitude)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alertas_zona ON alertas(zona_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_correos_estado ON correos_alerta(estado)")


def init_db():
    conn = get_conn()
    try:
        if is_postgres():
            _create_tables_postgres(conn)
        else:
            _create_tables_sqlite(conn)

        # Migraciones simples para bases antiguas
        if not _has_column(conn, "zonas", "usuario_id"):
            conn.execute("ALTER TABLE zonas ADD COLUMN usuario_id INTEGER")
        if not _has_column(conn, "zonas", "contacto_email"):
            conn.execute("ALTER TABLE zonas ADD COLUMN contacto_email TEXT")

        conn.commit()
    finally:
        conn.close()


def seed_demo_data():
    conn = get_conn()
    try:
        user_count = conn.execute("SELECT COUNT(*) AS n FROM usuarios").fetchone()[0]
        if user_count == 0:
            conn.executemany("""
                INSERT INTO usuarios
                (nombre, email, telefono, organizacion, tipo_usuario, activo, creado_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [
                ("Usuario piloto", "correo@ejemplo.com", "+591", "CampoSeguro", "Piloto", 1, now_utc()),
                ("Responsable municipal", "municipio@ejemplo.com", "+591", "Municipio", "Institucional", 1, now_utc()),
            ])
            conn.commit()

        usuario_piloto = conn.execute("SELECT id FROM usuarios ORDER BY id LIMIT 1").fetchone()[0]

        zone_count = conn.execute("SELECT COUNT(*) AS n FROM zonas").fetchone()[0]
        if zone_count == 0:
            rows = [
                (usuario_piloto, "Santa Cruz de la Sierra", "correo@ejemplo.com", "Ciudad", "Santa Cruz", "Santa Cruz de la Sierra", -17.7833, -63.1821, DEFAULT_ZONE_RADIUS_KM, 1, now_utc()),
                (usuario_piloto, "San Ignacio de Velasco", "correo@ejemplo.com", "Municipio", "Santa Cruz", "San Ignacio de Velasco", -16.3700, -60.9600, DEFAULT_ZONE_RADIUS_KM, 1, now_utc()),
                (usuario_piloto, "Roboré", "correo@ejemplo.com", "Municipio", "Santa Cruz", "Roboré", -18.3333, -59.7667, DEFAULT_ZONE_RADIUS_KM, 1, now_utc()),
                (usuario_piloto, "San Matías", "correo@ejemplo.com", "Municipio", "Santa Cruz", "San Matías", -16.3667, -58.4000, DEFAULT_ZONE_RADIUS_KM, 1, now_utc()),
                (usuario_piloto, "Charagua Iyambae", "correo@ejemplo.com", "Municipio", "Santa Cruz", "Charagua Iyambae", -19.8000, -63.2200, DEFAULT_ZONE_RADIUS_KM, 1, now_utc()),
                (usuario_piloto, "Puerto Suárez", "correo@ejemplo.com", "Municipio", "Santa Cruz", "Puerto Suárez", -18.9500, -57.8000, DEFAULT_ZONE_RADIUS_KM, 1, now_utc()),
            ]
            conn.executemany("""
                INSERT INTO zonas
                (usuario_id, nombre_zona, contacto_email, tipo_zona, departamento, municipio, latitud, longitud, radio_km, activa, creada_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)

        conn.commit()
    finally:
        conn.close()


def rows_to_dicts(rows):
    return [dict(r) for r in rows]


def db_status():
    return {
        "backend": DB_BACKEND,
        "persistent": is_postgres(),
        "database_url_configured": bool(DATABASE_URL),
    }
