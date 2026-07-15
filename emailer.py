from datetime import datetime, timezone
import html
import re
import smtplib
from email.message import EmailMessage
import requests

from config import (
    OUTBOX_DIR, APP_PUBLIC_URL,
    EMAIL_ENABLED, SMTP_HOST, SMTP_PORT, SMTP_USE_SSL, SMTP_USE_TLS, SMTP_USER, SMTP_PASSWORD,
    SMTP_FROM, EMAIL_REPLY_TO, EMAIL_MIN_LEVEL, EMAIL_MAX_PER_ZONE,
    EMAIL_SEND_TIMEOUT_SECONDS, EMAIL_PROCESS_LIMIT, EMAIL_PROVIDER, RESEND_API_KEY,
    EMAIL_API_TIMEOUT_SECONDS, EMAIL_SUMMARY_MAX_ALERTS, EMAIL_DAILY_MAX_PER_RECIPIENT
)
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


def nivel_maximo(rows):
    if not rows:
        return "INFORMATIVO"
    return max([str(r["nivel"]).upper() for r in rows], key=nivel_rank_email)


def etiqueta_nivel(nivel):
    nivel = str(nivel or "INFORMATIVO").upper()
    if nivel == "CRITICO":
        return "CRÍTICO"
    if nivel == "ATENCION":
        return "ATENCIÓN"
    return "INFORMATIVO"


def recomendacion_por_nivel(nivel):
    nivel = str(nivel or "").upper()
    if nivel == "CRITICO":
        return "Verificar de forma prioritaria en campo, comunicar a responsables locales y revisar condiciones de propagación."
    if nivel == "ATENCION":
        return "Mantener seguimiento cercano, revisar viento, reportes locales y preparar comunicación preventiva."
    return "Mantener seguimiento preventivo y verificar si aparecen nuevos focos en las próximas horas."


def google_maps_url(lat, lon):
    return f"https://www.google.com/maps?q={lat},{lon}"


def construir_mensaje(row):
    maps_url = google_maps_url(row['latitude'], row['longitude'])
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
    Por defecto solo envía ATENCION/CRITICO y máximo EMAIL_MAX_PER_ZONE alertas por zona.
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
    """
    Prepara registros pendientes por alerta. En v3.6 el envío los agrupa en un solo resumen por destinatario.
    """
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
    if EMAIL_PROVIDER in ("resend", "resend_api"):
        return all([RESEND_API_KEY or SMTP_PASSWORD, SMTP_FROM])
    return all([SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM])


def resumen_rows_pendientes(conn, destinatario):
    return conn.execute("""
        SELECT c.id AS correo_id, c.destinatario, c.asunto, c.cuerpo, c.creado_utc,
               a.id AS alerta_id, a.nivel, a.distancia_km, a.creada_utc AS alerta_creada_utc,
               z.id AS zona_id, z.nombre_zona, z.municipio, z.departamento, z.radio_km,
               u.nombre AS usuario_nombre, u.email AS usuario_email, u.telefono AS usuario_telefono,
               f.latitude, f.longitude, f.acq_date, f.acq_time, f.fuente, f.satellite, f.instrument, f.confidence, f.frp
        FROM correos_alerta c
        JOIN alertas a ON a.id=c.alerta_id
        JOIN zonas z ON z.id=a.zona_id
        LEFT JOIN usuarios u ON u.id=z.usuario_id
        JOIN focos f ON f.id=a.foco_id
        WHERE c.estado='pendiente' AND c.destinatario=?
        ORDER BY CASE WHEN a.nivel='CRITICO' THEN 1 WHEN a.nivel='ATENCION' THEN 2 ELSE 3 END,
                 a.distancia_km ASC,
                 z.nombre_zona ASC
    """, (destinatario,)).fetchall()


def conteo_enviados_hoy(conn, destinatario):
    hoy = now_utc()[:10]
    row = conn.execute("""
        SELECT COUNT(DISTINCT enviado_utc) AS n
        FROM correos_alerta
        WHERE estado='enviado' AND destinatario=? AND enviado_utc LIKE ?
    """, (destinatario, hoy + "%")).fetchone()
    return int(row["n"] if row else 0)


def agrupar_por_zona(rows):
    grupos = {}
    for r in rows:
        key = r["zona_id"]
        grupos.setdefault(key, {"zona": r, "alertas": []})["alertas"].append(r)
    return list(grupos.values())


def construir_resumen_texto(rows, destinatario):
    total = len(rows)
    grupos = agrupar_por_zona(rows)
    crit = sum(1 for r in rows if str(r["nivel"]).upper() == "CRITICO")
    aten = sum(1 for r in rows if str(r["nivel"]).upper() == "ATENCION")
    info = sum(1 for r in rows if str(r["nivel"]).upper() == "INFORMATIVO")
    nivel_global = nivel_maximo(rows)
    min_dist = min([float(r["distancia_km"] or 0) for r in rows]) if rows else 0

    partes = [
        "CampoSeguro - resumen de alertas",
        "",
        f"Destinatario: {destinatario}",
        f"Nivel máximo: {etiqueta_nivel(nivel_global)}",
        f"Zonas con alertas: {len(grupos)}",
        f"Alertas registradas: {total}",
        f"Críticas: {crit} | Atención: {aten} | Informativas: {info}",
        f"Distancia mínima detectada: {min_dist:.2f} km",
        "",
        "Resumen por zona:",
    ]

    for g in grupos:
        zona = g["zona"]
        alertas = g["alertas"]
        nivel_zona = nivel_maximo(alertas)
        min_zona = min([float(a["distancia_km"] or 0) for a in alertas])
        partes.append("")
        partes.append(f"- {zona['nombre_zona']} ({zona['municipio'] or 'Sin municipio'})")
        partes.append(f"  Nivel máximo: {etiqueta_nivel(nivel_zona)}")
        partes.append(f"  Alertas: {len(alertas)}")
        partes.append(f"  Distancia mínima: {min_zona:.2f} km")

    partes.append("")
    partes.append(f"Detalle de focos priorizados (máximo {EMAIL_SUMMARY_MAX_ALERTS}):")
    for idx, r in enumerate(rows[:EMAIL_SUMMARY_MAX_ALERTS], 1):
        partes.append("")
        partes.append(f"{idx}. {etiqueta_nivel(r['nivel'])} - {r['nombre_zona']}")
        partes.append(f"   Distancia: {float(r['distancia_km'] or 0):.2f} km")
        partes.append(f"   Fecha/hora satelital: {r['acq_date']} {r['acq_time']}")
        partes.append(f"   Fuente: NASA FIRMS / {r['fuente']}")
        partes.append(f"   Coordenadas: {r['latitude']}, {r['longitude']}")
        partes.append(f"   Mapa: {google_maps_url(r['latitude'], r['longitude'])}")

    if total > EMAIL_SUMMARY_MAX_ALERTS:
        partes.append("")
        partes.append(f"Además existen {total - EMAIL_SUMMARY_MAX_ALERTS} alerta(s) adicionales. Revise el panel de CampoSeguro.")

    partes.append("")
    partes.append("Recomendación general:")
    partes.append(recomendacion_por_nivel(nivel_global))
    partes.append("")
    partes.append(f"Panel CampoSeguro: {APP_PUBLIC_URL}/cliente")
    partes.append("")
    partes.append("Aviso: CampoSeguro es una herramienta informativa basada en datos satelitales. No reemplaza verificación en campo, sistemas oficiales de emergencia ni protocolos institucionales. Toda alerta debe ser verificada con fuentes locales y autoridades competentes.")
    return "\n".join(partes)


def construir_resumen_html(rows, destinatario):
    total = len(rows)
    grupos = agrupar_por_zona(rows)
    crit = sum(1 for r in rows if str(r["nivel"]).upper() == "CRITICO")
    aten = sum(1 for r in rows if str(r["nivel"]).upper() == "ATENCION")
    info = sum(1 for r in rows if str(r["nivel"]).upper() == "INFORMATIVO")
    nivel_global = nivel_maximo(rows)
    min_dist = min([float(r["distancia_km"] or 0) for r in rows]) if rows else 0

    color = "#b91c1c" if nivel_global == "CRITICO" else "#c2410c" if nivel_global == "ATENCION" else "#1d4ed8"
    h = html.escape

    zona_cards = ""
    for g in grupos:
        zona = g["zona"]
        alertas = g["alertas"]
        nivel_zona = nivel_maximo(alertas)
        min_zona = min([float(a["distancia_km"] or 0) for a in alertas])
        zona_cards += f"""
        <tr>
          <td style="padding:10px;border-bottom:1px solid #e5e7eb;"><strong>{h(str(zona['nombre_zona']))}</strong><br><span style="color:#64748b;">{h(str(zona['municipio'] or 'Sin municipio'))}</span></td>
          <td style="padding:10px;border-bottom:1px solid #e5e7eb;">{h(etiqueta_nivel(nivel_zona))}</td>
          <td style="padding:10px;border-bottom:1px solid #e5e7eb;text-align:center;">{len(alertas)}</td>
          <td style="padding:10px;border-bottom:1px solid #e5e7eb;text-align:right;">{min_zona:.2f} km</td>
        </tr>"""

    detalle = ""
    for idx, r in enumerate(rows[:EMAIL_SUMMARY_MAX_ALERTS], 1):
        mapa = google_maps_url(r['latitude'], r['longitude'])
        detalle += f"""
        <div style="border:1px solid #e5e7eb;border-radius:14px;padding:14px;margin:12px 0;background:#ffffff;">
          <div style="font-size:13px;color:#64748b;">Foco priorizado #{idx}</div>
          <div style="font-size:18px;font-weight:800;color:#0f172a;">{h(etiqueta_nivel(r['nivel']))} · {h(str(r['nombre_zona']))}</div>
          <div style="margin-top:6px;color:#334155;line-height:1.55;">
            Distancia: <strong>{float(r['distancia_km'] or 0):.2f} km</strong><br>
            Fecha/hora satelital: <strong>{h(str(r['acq_date']))} {h(str(r['acq_time']))}</strong><br>
            Fuente: NASA FIRMS / {h(str(r['fuente']))}<br>
            Coordenadas: {h(str(r['latitude']))}, {h(str(r['longitude']))}
          </div>
          <div style="margin-top:12px;"><a href="{h(mapa)}" style="display:inline-block;background:#0f766e;color:#ffffff;text-decoration:none;padding:10px 14px;border-radius:10px;font-weight:700;">Ver foco en Google Maps</a></div>
        </div>"""

    extra = ""
    if total > EMAIL_SUMMARY_MAX_ALERTS:
        extra = f"<p style='color:#475569;'>Además existen {total - EMAIL_SUMMARY_MAX_ALERTS} alerta(s) adicionales. Revise el panel de CampoSeguro.</p>"

    return f"""
    <!doctype html>
    <html><body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;color:#0f172a;">
      <div style="max-width:760px;margin:0 auto;padding:24px;">
        <div style="background:linear-gradient(135deg,#064e3b,#15803d);color:#fff;padding:24px;border-radius:18px 18px 0 0;">
          <div style="font-size:28px;font-weight:900;">CampoSeguro</div>
          <div style="font-size:15px;opacity:.95;margin-top:4px;">Resumen inteligente de alertas de focos de calor</div>
        </div>
        <div style="background:#ffffff;padding:24px;border-radius:0 0 18px 18px;box-shadow:0 8px 24px rgba(15,23,42,.08);">
          <div style="border-left:6px solid {color};background:#f8fafc;padding:16px;border-radius:14px;margin-bottom:18px;">
            <div style="font-size:13px;color:#64748b;font-weight:700;">Nivel máximo detectado</div>
            <div style="font-size:26px;font-weight:900;color:{color};">{h(etiqueta_nivel(nivel_global))}</div>
            <div style="margin-top:6px;color:#334155;">{total} alerta(s) en {len(grupos)} zona(s). Distancia mínima: <strong>{min_dist:.2f} km</strong>.</div>
          </div>
          <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin:12px 0 18px 0;">
            <tr>
              <td style="padding:12px;background:#fee2e2;border-radius:12px;text-align:center;"><div style="font-size:12px;color:#7f1d1d;">Críticas</div><div style="font-size:26px;font-weight:900;color:#991b1b;">{crit}</div></td>
              <td style="width:8px;"></td>
              <td style="padding:12px;background:#ffedd5;border-radius:12px;text-align:center;"><div style="font-size:12px;color:#7c2d12;">Atención</div><div style="font-size:26px;font-weight:900;color:#c2410c;">{aten}</div></td>
              <td style="width:8px;"></td>
              <td style="padding:12px;background:#dbeafe;border-radius:12px;text-align:center;"><div style="font-size:12px;color:#1e3a8a;">Informativas</div><div style="font-size:26px;font-weight:900;color:#1d4ed8;">{info}</div></td>
            </tr>
          </table>
          <h2 style="font-size:20px;margin:20px 0 8px;">Resumen por zona</h2>
          <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border:1px solid #e5e7eb;border-radius:14px;overflow:hidden;">
            <thead><tr style="background:#f8fafc;color:#475569;"><th align="left" style="padding:10px;">Zona</th><th align="left" style="padding:10px;">Nivel</th><th style="padding:10px;">Alertas</th><th align="right" style="padding:10px;">Distancia mín.</th></tr></thead>
            <tbody>{zona_cards}</tbody>
          </table>
          <h2 style="font-size:20px;margin:22px 0 8px;">Focos priorizados</h2>
          {detalle}
          {extra}
          <div style="background:#ecfdf5;border:1px solid #bbf7d0;border-radius:14px;padding:14px;margin:18px 0;">
            <strong>Recomendación general:</strong><br>{h(recomendacion_por_nivel(nivel_global))}
          </div>
          <p style="margin:18px 0;"><a href="{h(APP_PUBLIC_URL + '/cliente')}" style="display:inline-block;background:#166534;color:#ffffff;text-decoration:none;padding:12px 18px;border-radius:12px;font-weight:800;">Entrar al panel CampoSeguro</a></p>
          <p style="font-size:12px;line-height:1.55;color:#64748b;border-top:1px solid #e5e7eb;padding-top:14px;">
            CampoSeguro es una herramienta informativa basada en datos satelitales. No reemplaza verificación en campo, sistemas oficiales de emergencia ni protocolos institucionales. Toda alerta debe ser verificada con fuentes locales y autoridades competentes.
          </p>
        </div>
      </div>
    </body></html>
    """


def construir_correo_resumen(rows, destinatario):
    total = len(rows)
    zonas = len(agrupar_por_zona(rows))
    nivel = nivel_maximo(rows)
    asunto = f"CampoSeguro: resumen {etiqueta_nivel(nivel)} · {total} alerta(s) en {zonas} zona(s)"
    return {
        "id": "resumen_" + clean_filename(destinatario),
        "destinatario": destinatario,
        "asunto": asunto,
        "cuerpo": construir_resumen_texto(rows, destinatario),
        "html": construir_resumen_html(rows, destinatario),
    }


def escribir_outbox(row):
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    fname = OUTBOX_DIR / f"alerta_{clean_filename(row.get('id','resumen'))}_{clean_filename(row['destinatario'])}.txt"
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
    if row.get("html"):
        payload["html"] = row["html"]
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
    if row.get('html'):
        msg.add_alternative(row['html'], subtype='html')

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

Si recibes este mensaje, el envío por Resend API está funcionando correctamente.

CampoSeguro es una herramienta informativa. No reemplaza verificación en campo ni sistemas oficiales de emergencia.
""",
        "html": f"""
        <div style='font-family:Arial,Helvetica,sans-serif;max-width:640px;margin:auto;background:#f8fafc;padding:24px;'>
          <div style='background:linear-gradient(135deg,#064e3b,#15803d);color:white;padding:22px;border-radius:16px 16px 0 0;'>
            <h1 style='margin:0;'>CampoSeguro</h1><p style='margin:6px 0 0;'>Correo de prueba</p>
          </div>
          <div style='background:#fff;padding:22px;border-radius:0 0 16px 16px;'>
            <p>Hola,</p><p>Este es un correo de prueba de CampoSeguro.</p>
            <p><strong>Si recibes este mensaje, el envío por Resend API está funcionando correctamente.</strong></p>
            <p><a href='{html.escape(APP_PUBLIC_URL)}' style='display:inline-block;background:#166534;color:#fff;padding:12px 16px;border-radius:10px;text-decoration:none;font-weight:bold;'>Entrar a CampoSeguro</a></p>
            <p style='font-size:12px;color:#64748b;'>CampoSeguro es una herramienta informativa. No reemplaza verificación en campo ni sistemas oficiales de emergencia.</p>
          </div>
        </div>
        """
    }
    enviar_email_real(row)
    return True


def marcar_rows(conn, rows, estado, error=None):
    fecha = now_utc()
    for r in rows:
        conn.execute(
            "UPDATE correos_alerta SET estado=?, error=?, enviado_utc=? WHERE id=?",
            (estado, error, fecha, r['correo_id'])
        )


def procesar_correos_pendientes(limit=None):
    """
    v3.6: procesa un resumen por destinatario. Si hay 20 alertas para un usuario, se envía un solo correo resumen.
    """
    if limit is None:
        limit = EMAIL_PROCESS_LIMIT
    conn = get_conn()
    destinatarios = conn.execute("""
        SELECT destinatario, MIN(creado_utc) AS primero
        FROM correos_alerta
        WHERE estado='pendiente'
        GROUP BY destinatario
        ORDER BY primero ASC
        LIMIT ?
    """, (limit,)).fetchall()

    procesados = enviados = outbox = errores = bloqueados = 0
    for d in destinatarios:
        destinatario = d['destinatario']
        rows = resumen_rows_pendientes(conn, destinatario)
        if not rows:
            continue
        procesados += len(rows)
        try:
            if not email_operativo(destinatario):
                marcar_rows(conn, rows, 'bloqueado', 'Correo de prueba/no operativo bloqueado')
                bloqueados += len(rows)
                continue

            if EMAIL_DAILY_MAX_PER_RECIPIENT > 0 and conteo_enviados_hoy(conn, destinatario) >= EMAIL_DAILY_MAX_PER_RECIPIENT:
                marcar_rows(conn, rows, 'bloqueado', f'Límite diario de {EMAIL_DAILY_MAX_PER_RECIPIENT} correo(s) alcanzado para este destinatario')
                bloqueados += len(rows)
                continue

            resumen = construir_correo_resumen(rows, destinatario)
            if smtp_config_ok():
                enviar_email_real(resumen)
                marcar_rows(conn, rows, 'enviado', None)
                enviados += 1
            else:
                path = escribir_outbox(resumen)
                marcar_rows(conn, rows, 'outbox', f'Modo seguro/local. Archivo generado: {path}')
                outbox += 1
        except Exception as exc:
            marcar_rows(conn, rows, 'error', str(exc))
            errores += len(rows)

    conn.commit()
    conn.close()
    return {
        'procesados': procesados,
        'enviados': enviados,
        'outbox': outbox,
        'errores': errores,
        'bloqueados': bloqueados,
        'smtp_activo': smtp_config_ok(),
        'modo_resumen': True,
    }


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
