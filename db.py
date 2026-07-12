import sqlite3
from datetime import datetime, timezone
from config import DB_PATH, DEFAULT_ZONE_RADIUS_KM


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _has_column(cur, table, column):
    cols = [row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    return column in cols


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
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

    cur.execute("""
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

    cur.execute("""
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

    cur.execute("""
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

    cur.execute("""
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

    # Migraciones simples para bases antiguas
    if not _has_column(cur, "zonas", "usuario_id"):
        cur.execute("ALTER TABLE zonas ADD COLUMN usuario_id INTEGER")
    if not _has_column(cur, "zonas", "contacto_email"):
        cur.execute("ALTER TABLE zonas ADD COLUMN contacto_email TEXT")

    conn.commit()
    conn.close()


def seed_demo_data():
    conn = get_conn()
    cur = conn.cursor()

    user_count = cur.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
    if user_count == 0:
        cur.executemany("""
            INSERT INTO usuarios
            (nombre, email, telefono, organizacion, tipo_usuario, activo, creado_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            ("Usuario piloto", "correo@ejemplo.com", "+591", "CampoSeguro", "Piloto", 1, now_utc()),
            ("Responsable municipal", "municipio@ejemplo.com", "+591", "Municipio", "Institucional", 1, now_utc()),
        ])

    usuario_piloto = cur.execute("SELECT id FROM usuarios ORDER BY id LIMIT 1").fetchone()[0]

    zone_count = cur.execute("SELECT COUNT(*) FROM zonas").fetchone()[0]
    if zone_count == 0:
        rows = [
            (usuario_piloto, "Santa Cruz de la Sierra", "correo@ejemplo.com", "Ciudad", "Santa Cruz", "Santa Cruz de la Sierra", -17.7833, -63.1821, DEFAULT_ZONE_RADIUS_KM, 1, now_utc()),
            (usuario_piloto, "San Ignacio de Velasco", "correo@ejemplo.com", "Municipio", "Santa Cruz", "San Ignacio de Velasco", -16.3700, -60.9600, DEFAULT_ZONE_RADIUS_KM, 1, now_utc()),
            (usuario_piloto, "Roboré", "correo@ejemplo.com", "Municipio", "Santa Cruz", "Roboré", -18.3333, -59.7667, DEFAULT_ZONE_RADIUS_KM, 1, now_utc()),
            (usuario_piloto, "San Matías", "correo@ejemplo.com", "Municipio", "Santa Cruz", "San Matías", -16.3667, -58.4000, DEFAULT_ZONE_RADIUS_KM, 1, now_utc()),
            (usuario_piloto, "Charagua Iyambae", "correo@ejemplo.com", "Municipio", "Santa Cruz", "Charagua Iyambae", -19.8000, -63.2200, DEFAULT_ZONE_RADIUS_KM, 1, now_utc()),
            (usuario_piloto, "Puerto Suárez", "correo@ejemplo.com", "Municipio", "Santa Cruz", "Puerto Suárez", -18.9500, -57.8000, DEFAULT_ZONE_RADIUS_KM, 1, now_utc()),
        ]
        cur.executemany("""
            INSERT INTO zonas
            (usuario_id, nombre_zona, contacto_email, tipo_zona, departamento, municipio, latitud, longitud, radio_km, activa, creada_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)

    conn.commit()
    conn.close()


def rows_to_dicts(rows):
    return [dict(r) for r in rows]