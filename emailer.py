from datetime import datetime, timezone
import re
import smtplib
from email.message import EmailMessage
import requests

from config import OUTBOX_DIR, EMAIL_ENABLED, SMTP_HOST, SMTP_PORT, SMTP_USE_SSL, SMTP_USE_TLS, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, EMAIL_REPLY_TO, EMAIL_MIN_LEVEL, EMAIL_MAX_PER_ZONE, EMAIL_SEND_TIMEOUT_SECONDS, EMAIL_PROCESS_LIMIT, EMAIL_PROVIDER, RESEND_API_KEY, EMAIL_API_TIMEOUT_SECONDS
from db import get_conn


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def clean_filename(text):
    text = re.sub(r"[^A-Za-z0-9_\-\.]+", "_", str(text))
    return text[:160]

def email_operativo(email):
    """Evita enviar a correos de ejemplo o direcciones claramente inválidas."""
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return False
    bloqueados = [
        "@ejemplo.com",
        "@example.com",
        "sin-correo@camposeguro.local",
        "correo@ejemplo.com",
        "municipio@ejemplo.com",
    ]
    return not any(email.endswith(b) or email == b for b in bloqueados)




def nivel_rank_email(nivel):
    orden = {"INFORMATIVO": 1, "ATENCION": 2, "CRITICO": 3}
    return orden.get(str(nivel or "").upper(), 0)


def nivel_permitido_email(nivel):
    return nivel_rank_email(nivel) >= nivel_rank_email(EMAIL_MIN_LEVEL)



def recomendacion_por_nivel(nivel):
    if nivel == "CRITICO":
        return "Verificar de forma prioritaria en campo, comunicar a responsables locales y revisar condiciones de propagación."
    if nivel == "ATENCION":
        return "Mantener seguimiento cercano, revisar viento, reportes locales y preparar comunicación preventiva."
    return "Mantener seguimiento preventivo y verificar si aparecen nuevos focos en las próximas horas."


def construir_mensaje(row):
    maps_url = f"https://www.google.com/maps?q={row['latitude']},{row['longitude']}"
    return f"""CampoSeguro informa que se detectó un foco de calor cercano a una zona monitoreada.

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
    """
    Devuelve alertas elegibles para correo, evitando saturación.
    Por defecto solo envía ATENCION/CRITICO y máximo 1 alerta por zona.
    """
    conn = get_conn()
    rows = conn.execute("""
        SELECT a.id AS alerta_id, a.nivel, a.distancia_km,
               z.id AS zona_id, z.nombre_zona, z.municipio, z.contacto_email,
               u.nombre AS usuario_nombre, u.email AS usuario_email, u.telefono AS usuario_telefono,
               f.latitude, f.longitude, f.acq_date, f.acq_time, f.fuente
        FROM alertas a
        JOIN zonas z ON z.id=a.zona_id
        LEFT JOIN usuarios u ON u.id=z.usuario_id
        JOIN focos f ON f.id=a.foco_id
        WHERE NOT EXISTS (SELECT 1 FROM correos_alerta c WHERE c.alerta_id=a.id)
        ORDER BY CASE WHEN a.nivel='CRITICO' THEN 1 WHEN a.nivel='ATENCION' THEN 2 ELSE 3 END,
                 z.id ASC,
                 a.distancia_km ASC
    """).fetchall()
    conn.close()

    filtradas = []
    por_zona = {}

    for r in rows:
        if not nivel_permitido_email(r["nivel"]):
            continue

        zona_id = r["zona_id"]
        usados = por_zona.get(zona_id, 0)
        if EMAIL_MAX_PER_ZONE > 0 and usados >= EMAIL_MAX_PER_ZONE:
            continue

        filtradas.append(r)
        por_zona[zona_id] = usados + 1

    return filtradas


def preparar_correos_pendientes():
    rows = alerta_rows_no_encoladas()
    conn = get_conn()
    creados = 0
    for r in rows:
        destinatario = (r['usuario_email'] or r['contacto_email'] or '').strip()
        if not email_operativo(destinatario):
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
    if not EMAIL_ENABLED:
        return False
    if EMAIL_PROVIDER == "resend_api":
        return all([RESEND_API_KEY, SMTP_FROM])
    if EMAIL_PROVIDER == "resend":
        # En v3.5 usamos la API HTTPS de Resend aunque las variables SMTP sigan presentes.
        return all([SMTP_PASSWORD or RESEND_API_KEY, SMTP_FROM])
    return all([SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM])


def escribir_outbox(row):
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    fname = OUTBOX_DIR / f"alerta_{row['id']}_{clean_filename(row['destinatario'])}.txt"
    fname.write_text(f"TO: {row['destinatario']}\nSUBJECT: {row['asunto']}\n\n{row['cuerpo']}", encoding='utf-8')
    return str(fname)


def enviar_email_resend_api(row):
    """
    Envío estable por API HTTPS de Resend.
    Evita los cuelgues ocasionales del SMTP en Render/Cloudflare.
    """
    api_key = (RESEND_API_KEY or SMTP_PASSWORD or "").strip()
    if not api_key:
        raise RuntimeError("Falta RESEND_API_KEY o SMTP_PASSWORD con la API Key de Resend.")

    payload = {
        "from": SMTP_FROM,
        "to": [row["destinatario"]],
        "subject": row["asunto"],
        "text": row["cuerpo"],
    }
    if EMAIL_REPLY_TO:
        payload["reply_to"] = [EMAIL_REPLY_TO]

    r = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=EMAIL_API_TIMEOUT_SECONDS,
    )
    if r.status_code >= 300:
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        raise RuntimeError(f"Resend API error {r.status_code}: {detail}")
    return r.json()


def enviar_email_smtp(row):
    msg = EmailMessage()
    msg['From'] = SMTP_FROM
    msg['To'] = row['destinatario']
    msg['Subject'] = row['asunto']
    if EMAIL_REPLY_TO:
        msg['Reply-To'] = EMAIL_REPLY_TO
    msg.set_content(row['cuerpo'])

    if SMTP_USE_SSL:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=EMAIL_SEND_TIMEOUT_SECONDS) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=EMAIL_SEND_TIMEOUT_SECONDS) as server:
            if SMTP_USE_TLS:
                server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)


def enviar_email_real(row):
    if EMAIL_PROVIDER in ("resend", "resend_api"):
        return enviar_email_resend_api(row)
    return enviar_email_smtp(row)


def enviar_correo_prueba(destinatario):
    row = {
        "destinatario": destinatario,
        "asunto": "Prueba CampoSeguro - correo de alertas",
        "cuerpo": """Hola,

Este es un correo de prueba de CampoSeguro.

Si recibes este mensaje, el envío SMTP está funcionando correctamente.

Configuración recomendada para Resend:
- SMTP_HOST=smtp.resend.com
- SMTP_PORT=465
- SMTP_USE_SSL=true
- SMTP_USE_TLS=false
- SMTP_USER=resend
- SMTP_FROM=CampoSeguro <alertas@camposeguro.app>

CampoSeguro es una herramienta informativa. No reemplaza verificación en campo ni sistemas oficiales de emergencia.
"""
    }
    enviar_email_real(row)
    return True


def procesar_correos_pendientes(limit=None):
    if limit is None:
        limit = EMAIL_PROCESS_LIMIT
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM correos_alerta
        WHERE estado='pendiente'
        ORDER BY creado_utc ASC
        LIMIT ?
    """, (limit,)).fetchall()
    enviados = outbox = errores = bloqueados = 0
    for r in rows:
        try:
            if not email_operativo(r['destinatario']):
                conn.execute("UPDATE correos_alerta SET estado='bloqueado', error=?, enviado_utc=? WHERE id=?", ("Correo de prueba/no operativo bloqueado", now_utc(), r['id']))
                bloqueados += 1
                continue
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
    return {'procesados': len(rows), 'enviados': enviados, 'outbox': outbox, 'errores': errores, 'bloqueados': bloqueados, 'smtp_activo': smtp_config_ok()}


def limpiar_correos_prueba_y_errores():
    conn = get_conn()
    antes = conn.execute('SELECT COUNT(*) FROM correos_alerta').fetchone()[0]
    # Elimina pruebas, errores antiguos y outbox local para dejar la cola limpia.
    conn.execute("""
        DELETE FROM correos_alerta
        WHERE estado IN ('error', 'outbox', 'bloqueado')
           OR LOWER(destinatario) LIKE ?
           OR LOWER(destinatario) LIKE ?
           OR LOWER(destinatario) = ?
    """, ('%ejemplo.com%', '%example.com%', 'sin-correo@camposeguro.local'))
    conn.commit()
    despues = conn.execute('SELECT COUNT(*) FROM correos_alerta').fetchone()[0]
    conn.close()
    return {'eliminados': antes - despues, 'antes': antes, 'despues': despues}

def estadisticas_correos():
    conn = get_conn()
    stats = {}
    for estado in ['pendiente', 'enviado', 'outbox', 'error', 'bloqueado']:
        stats[estado if estado != 'pendiente' else 'pendientes'] = conn.execute('SELECT COUNT(*) FROM correos_alerta WHERE estado=?', (estado,)).fetchone()[0]
    stats['total'] = conn.execute('SELECT COUNT(*) FROM correos_alerta').fetchone()[0]
    stats['enviados'] = stats.pop('enviado')
    stats['errores'] = stats.pop('error')
    stats['bloqueados'] = stats.pop('bloqueado')
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