from datetime import datetime, timezone
import re
import smtplib
from email.message import EmailMessage

from config import OUTBOX_DIR, EMAIL_ENABLED, SMTP_HOST, SMTP_PORT, SMTP_USE_TLS, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
from db import get_conn


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def clean_filename(text):
    text = re.sub(r"[^A-Za-z0-9_\-\.]+", "_", str(text))
    return text[:160]


def recomendacion_por_nivel(nivel):
    if nivel == "CRITICO":
        return "Verificar de forma prioritaria en campo, comunicar a responsables locales y revisar condiciones de propagación."
    if nivel == "ATENCION":
        return "Mantener seguimiento cercano, revisar viento, reportes locales y preparar comunicación preventiva."
    return "Mantener seguimiento preventivo y verificar si aparecen nuevos focos en las próximas horas."


def construir_mensaje(row):
    maps_url = f"https://www.google.com/maps?q={row['latitude']},{row['longitude']}"
    return f"""CampoSeguro informa que se detectó un foco de calor cercano a una zona registrada.

Nivel de alerta: {row['nivel']}
Zona: {row['nombre_zona']}
Usuario/responsable: {row['usuario_nombre'] or 'No registrado'}
Municipio: {row['municipio'] or 'No registrado'}
Distancia aproximada: {row['distancia_km']} km
Fuente: NASA FIRMS / {row['fuente']}
Fecha/hora satelital: {row['acq_date']} {row['acq_time']}

Coordenadas del foco:
Latitud: {row['latitude']}
Longitud: {row['longitude']}

Mapa:
{maps_url}

Recomendación:
{recomendacion_por_nivel(row['nivel'])}

Aviso:
CampoSeguro es una herramienta informativa basada en datos satelitales. No reemplaza verificación en campo, sistemas oficiales de emergencia ni protocolos institucionales. Toda alerta debe ser verificada con fuentes locales y autoridades competentes.
"""


def alerta_rows_no_encoladas():
    conn = get_conn()
    rows = conn.execute("""
        SELECT a.id AS alerta_id, a.nivel, a.distancia_km,
               z.nombre_zona, z.municipio, z.contacto_email,
               u.nombre AS usuario_nombre, u.email AS usuario_email, u.telefono AS usuario_telefono,
               f.latitude, f.longitude, f.acq_date, f.acq_time, f.fuente
        FROM alertas a
        JOIN zonas z ON z.id=a.zona_id
        LEFT JOIN usuarios u ON u.id=z.usuario_id
        JOIN focos f ON f.id=a.foco_id
        WHERE NOT EXISTS (SELECT 1 FROM correos_alerta c WHERE c.alerta_id=a.id)
        ORDER BY CASE WHEN a.nivel='CRITICO' THEN 1 WHEN a.nivel='ATENCION' THEN 2 ELSE 3 END, a.distancia_km ASC
    """).fetchall()
    conn.close()
    return rows


def preparar_correos_pendientes():
    rows = alerta_rows_no_encoladas()
    conn = get_conn()
    creados = 0
    for r in rows:
        destinatario = (r['usuario_email'] or r['contacto_email'] or '').strip()
        if not destinatario or destinatario == 'sin-correo@camposeguro.local':
            continue
        asunto = f"CampoSeguro: alerta {r['nivel']} para {r['nombre_zona']}"
        cuerpo = construir_mensaje(r)
        cur = conn.execute("""
            INSERT OR IGNORE INTO correos_alerta
            (alerta_id, destinatario, asunto, cuerpo, estado, error, creado_utc)
            VALUES (?, ?, ?, ?, 'pendiente', NULL, ?)
        """, (r['alerta_id'], destinatario, asunto, cuerpo, now_utc()))
        if cur.rowcount:
            creados += 1
    conn.commit()
    conn.close()
    return creados


def smtp_config_ok():
    return all([EMAIL_ENABLED, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM])


def escribir_outbox(row):
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    fname = OUTBOX_DIR / f"alerta_{row['id']}_{clean_filename(row['destinatario'])}.txt"
    fname.write_text(f"TO: {row['destinatario']}\nSUBJECT: {row['asunto']}\n\n{row['cuerpo']}", encoding='utf-8')
    return str(fname)


def enviar_email_real(row):
    msg = EmailMessage()
    msg['From'] = SMTP_FROM
    msg['To'] = row['destinatario']
    msg['Subject'] = row['asunto']
    msg.set_content(row['cuerpo'])
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=60) as server:
        if SMTP_USE_TLS:
            server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)


def procesar_correos_pendientes():
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM correos_alerta
        WHERE estado IN ('pendiente', 'error')
        ORDER BY creado_utc ASC
    """).fetchall()
    enviados = outbox = errores = 0
    for r in rows:
        try:
            if smtp_config_ok():
                enviar_email_real(r)
                conn.execute("UPDATE correos_alerta SET estado='enviado', error=NULL, enviado_utc=? WHERE id=?", (now_utc(), r['id']))
                enviados += 1
            else:
                path = escribir_outbox(r)
                conn.execute("UPDATE correos_alerta SET estado='outbox', error=?, enviado_utc=? WHERE id=?", (f"Modo seguro/local. Archivo generado: {path}", now_utc(), r['id']))
                outbox += 1
        except Exception as exc:
            conn.execute("UPDATE correos_alerta SET estado='error', error=? WHERE id=?", (str(exc), r['id']))
            errores += 1
    conn.commit()
    conn.close()
    return {'procesados': len(rows), 'enviados': enviados, 'outbox': outbox, 'errores': errores, 'smtp_activo': smtp_config_ok()}


def estadisticas_correos():
    conn = get_conn()
    stats = {}
    for estado in ['pendiente', 'enviado', 'outbox', 'error']:
        stats[estado if estado != 'pendiente' else 'pendientes'] = conn.execute('SELECT COUNT(*) FROM correos_alerta WHERE estado=?', (estado,)).fetchone()[0]
    stats['total'] = conn.execute('SELECT COUNT(*) FROM correos_alerta').fetchone()[0]
    stats['enviados'] = stats.pop('enviado')
    stats['errores'] = stats.pop('error')
    conn.close()
    return stats


def listar_correos(limit=200):
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.*, a.nivel, z.nombre_zona, z.municipio
        FROM correos_alerta c
        JOIN alertas a ON a.id=c.alerta_id
        JOIN zonas z ON z.id=a.zona_id
        ORDER BY c.creado_utc DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return rows