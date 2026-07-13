from datetime import datetime, timezone
import html
import json
import traceback
import math
import time
import hmac
import hashlib
import csv
from io import StringIO
from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from config import (
    FIRMS_MAP_KEY, FIRMS_AREA_BBOX, FIRMS_DAY_RANGE, FIRMS_SOURCES,
    DB_BACKEND,
    EMAIL_ENABLED, SMTP_HOST, SMTP_PORT, SMTP_USE_SSL, SMTP_USE_TLS, SMTP_USER, SMTP_FROM, EMAIL_REPLY_TO,
    AUTH_ENABLED, ADMIN_USER, ADMIN_PASSWORD, SESSION_SECRET,
    AUTH_COOKIE_NAME, AUTH_COOKIE_SECURE, AUTH_SESSION_HOURS, ALERT_EVALUATION_HOURS,
    CLIENT_USER, CLIENT_PASSWORD, CLIENT_NAME,
    DEFAULT_ZONE_RADIUS_KM, CLIENT_MIN_RADIUS_KM, CLIENT_MAX_RADIUS_KM,
    EMAIL_MIN_LEVEL, EMAIL_MAX_PER_ZONE,
    AUTO_MONITOR_ENABLED, AUTO_MONITOR_INTERVAL_MINUTES, AUTO_MONITOR_RUN_ON_STARTUP,
    AUTO_MONITOR_START_DELAY_SECONDS, MONITOR_SECRET
)
from db import init_db, seed_demo_data, get_conn, rows_to_dicts, db_status
from monitor import run_monitoring, clear_data, recalcular_alertas_existentes
from emailer import preparar_correos_pendientes, procesar_correos_pendientes, estadisticas_correos, listar_correos, smtp_config_ok, enviar_correo_prueba
from firms_api import test_source, masked_key, AREA_PRESETS, API_REGION_LABEL
from auto_monitor import start_background_monitor, get_auto_monitor_status, run_monitor_once


app = FastAPI(title="CampoSeguro v3.3")


PUBLIC_PATHS = {"/login", "/logout", "/landing", "/healthz", "/favicon.ico", "/cron/monitor"}
CLIENT_ALLOWED_PREFIXES = ("/cliente",)
CLIENT_ALLOWED_EXACT = {"/logout", "/healthz"}


def auth_configured():
    return bool(ADMIN_PASSWORD)


def client_configured():
    return bool(CLIENT_PASSWORD)


def make_session_token(username: str, role: str) -> str:
    exp = int(time.time()) + (AUTH_SESSION_HOURS * 3600)
    msg = f"{role}|{username}|{exp}"
    sig = hmac.new(SESSION_SECRET.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{role}|{username}|{exp}|{sig}"


def verify_session_token(token: str):
    try:
        role, username, exp_raw, sig = token.split("|", 3)
        exp = int(exp_raw)
        if exp < int(time.time()):
            return None

        if role not in ["admin", "cliente"]:
            return None

        if role == "admin" and username != ADMIN_USER:
            return None

        if role == "cliente" and username != CLIENT_USER:
            return None

        msg = f"{role}|{username}|{exp}"
        expected = hmac.new(SESSION_SECRET.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None

        return {"username": username, "role": role}
    except Exception:
        return None


def current_user(request: Request):
    token = request.cookies.get(AUTH_COOKIE_NAME, "")
    return verify_session_token(token) if token else None


def is_client_allowed_path(path: str) -> bool:
    if path in CLIENT_ALLOWED_EXACT:
        return True
    return path.startswith(CLIENT_ALLOWED_PREFIXES)


def safe_next_url(next_url: str) -> str:
    if not next_url or not next_url.startswith("/") or next_url.startswith("//"):
        return "/"
    return next_url


def authenticate_credentials(username: str, password: str):
    username = (username or "").strip()

    if ADMIN_PASSWORD and username == ADMIN_USER and hmac.compare_digest(password, ADMIN_PASSWORD):
        return {"username": ADMIN_USER, "role": "admin"}

    if CLIENT_PASSWORD and username == CLIENT_USER and hmac.compare_digest(password, CLIENT_PASSWORD):
        return {"username": CLIENT_USER, "role": "cliente"}

    return None


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    path = request.url.path

    if not AUTH_ENABLED:
        return await call_next(request)

    if path in PUBLIC_PATHS or path.startswith("/login"):
        return await call_next(request)

    user = current_user(request)
    if user:
        if user["role"] == "cliente" and not is_client_allowed_path(path):
            return RedirectResponse(url="/cliente", status_code=303)
        return await call_next(request)

    next_url = request.url.path
    if request.url.query:
        next_url += "?" + request.url.query

    return RedirectResponse(url=f"/login?next={quote(next_url, safe='')}", status_code=303)


def login_page_html(next_url="/", error=""):
    configured = auth_configured()
    err_html = f"<div class='login-error'>{esc(error)}</div>" if error else ""
    config_warning = "" if configured else """
      <div class="login-warning">
        Falta configurar <strong>ADMIN_PASSWORD</strong> en Render. Para acceso de cliente, configura también <strong>CLIENT_PASSWORD</strong>.
      </div>
    """
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>CampoSeguro | Iniciar sesión</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {{ --verde-oscuro:#0f3023; --verde:#1f6f43; --verde-suave:#e9f5ee; --texto:#142026; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; min-height:100vh; font-family:Inter,Arial,sans-serif; background:linear-gradient(135deg,#0f3023,#1f6f43); display:flex; align-items:center; justify-content:center; padding:24px; color:var(--texto); }}
.login-card {{ width:100%; max-width:460px; background:white; border-radius:24px; padding:30px; box-shadow:0 24px 80px rgba(0,0,0,.25); }}
.brand {{ color:#14532d; font-weight:900; font-size:32px; margin:0; letter-spacing:-.6px; }}
.subtitle {{ color:#475569; margin:8px 0 24px; line-height:1.45; }}
label {{ display:block; margin-top:14px; font-weight:800; }}
input {{ width:100%; padding:13px; margin-top:6px; border:1px solid #cbd5e1; border-radius:12px; font-size:16px; }}
button {{ width:100%; margin-top:22px; background:var(--verde); color:white; border:0; border-radius:14px; padding:14px; font-weight:900; font-size:16px; cursor:pointer; }}
.login-error {{ background:#fee2e2; color:#991b1b; padding:12px; border-radius:12px; margin-bottom:14px; font-weight:700; }}
.login-warning {{ background:#fff7ed; color:#92400e; padding:12px; border-left:5px solid #f97316; border-radius:12px; margin-bottom:14px; }}
.help {{ margin-top:18px; font-size:13px; color:#64748b; line-height:1.45; }}
</style>
</head>
<body>
  <div class="login-card">
    <h1 class="brand">CampoSeguro</h1>
    <p class="subtitle">Acceso protegido a la plataforma de alerta temprana informativa de focos de calor.</p>
    {config_warning}
    {err_html}
    <form method="post" action="/login">
      <input type="hidden" name="next_url" value="{esc(safe_next_url(next_url))}">
      <label>Usuario</label>
      <input name="username" autocomplete="username" autofocus required>
      <label>Contraseña</label>
      <input name="password" type="password" autocomplete="current-password" required>
      <button type="submit">Entrar</button>
    </form>
    <div class="help">Administrador: panel completo. Cliente: vista simple y solo lectura. CampoSeguro es una herramienta informativa.</div>
  </div>
</body>
</html>"""


@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request, next: str = "/", error: str = ""):
    user = current_user(request)
    if user:
        if user["role"] == "cliente":
            return RedirectResponse("/cliente", status_code=303)
        return RedirectResponse(safe_next_url(next), status_code=303)
    return login_page_html(next_url=next, error=error)


@app.post("/login")
def login_post(username: str = Form(...), password: str = Form(...), next_url: str = Form("/")):
    next_url = safe_next_url(next_url)

    if not auth_configured():
        return RedirectResponse(url=f"/login?error={quote('ADMIN_PASSWORD no configurado en Render')}&next={quote(next_url, safe='')}", status_code=303)

    user = authenticate_credentials(username, password)

    if user:
        destination = next_url
        if user["role"] == "cliente":
            destination = "/cliente"

        response = RedirectResponse(destination, status_code=303)
        response.set_cookie(
            AUTH_COOKIE_NAME,
            make_session_token(user["username"], user["role"]),
            max_age=AUTH_SESSION_HOURS * 3600,
            httponly=True,
            secure=AUTH_COOKIE_SECURE,
            samesite="lax",
        )
        return response

    return RedirectResponse(url=f"/login?error={quote('Usuario o contraseña incorrectos')}&next={quote(next_url, safe='')}", status_code=303)


@app.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(AUTH_COOKIE_NAME)
    return response


@app.get("/healthz")
def healthz():
    return {"status": "ok", "app": "CampoSeguro", "auth": AUTH_ENABLED}



def esc(x):
    return html.escape("" if x is None else str(x))


def recomendacion_por_nivel(nivel):
    if nivel == "CRITICO":
        return "Verificar de forma prioritaria en campo, comunicar a responsables locales y revisar condiciones de propagación."
    if nivel == "ATENCION":
        return "Mantener seguimiento cercano, revisar viento, reportes locales y preparar comunicación preventiva."
    return "Mantener seguimiento preventivo y verificar si aparecen nuevos focos en las próximas horas."


def mensaje_alerta(a):
    return (
        f"CampoSeguro informa que se detectó un foco de calor a aproximadamente {a['distancia_km']} km "
        f"de la zona {a['nombre_zona']}, municipio {a['municipio']}, según datos FIRMS/{a['fuente']} "
        f"del {a['acq_date']} a horas {a['acq_time']}. Nivel de alerta: {a['nivel']}. "
        f"Recomendación: {recomendacion_por_nivel(a['nivel'])} "
        "Esta información es de carácter preventivo y debe ser verificada con fuentes locales y autoridades competentes."
    )


def layout(title, body):
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>{esc(title)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {{
  --verde-oscuro:#0f3023; --verde:#1f6f43; --verde-suave:#e9f5ee;
  --gris:#f4f6f7; --texto:#142026; --alerta:#dc2626; --fuego:#f97316; --azul:#2563eb;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:Inter,Arial,sans-serif; background:var(--gris); color:var(--texto); }}
header {{ background:linear-gradient(135deg,#0f3023,#1f6f43); color:white; padding:24px 32px 20px; }}
header h1 {{ margin:0; font-size:30px; letter-spacing:-0.5px; }}
header p {{ margin:6px 0 0; opacity:.92; }}
nav {{ background:#184a34; padding:12px 32px; display:flex; gap:18px; flex-wrap:wrap; }}
nav a {{ color:white; text-decoration:none; font-weight:700; }}
main {{ padding:26px 32px; }}
.hero {{ background:white; border-radius:18px; padding:26px; margin-bottom:22px; box-shadow:0 8px 30px rgba(0,0,0,.08); display:grid; grid-template-columns:1.5fr 1fr; gap:22px; align-items:center; }}
.hero h2 {{ margin:0 0 10px; font-size:30px; }}
.hero p {{ font-size:17px; line-height:1.45; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:16px; }}
.card {{ background:white; border-radius:16px; padding:20px; margin-bottom:18px; box-shadow:0 4px 18px rgba(0,0,0,.07); }}
.metric-label {{ color:#52616a; font-weight:700; font-size:14px; }}
.metric {{ font-size:36px; font-weight:900; margin-top:6px; }}
.button,button {{ background:var(--verde); color:white; border:0; border-radius:12px; padding:12px 18px; font-weight:800; cursor:pointer; text-decoration:none; display:inline-block; font-size:15px; }}
.button.secondary,button.secondary {{ background:#64748b; }}
.button.danger,button.danger {{ background:#991b1b; }}
.button.light {{ background:var(--verde-suave); color:#14532d; }}
table {{ border-collapse:collapse; width:100%; background:white; }}
th,td {{ border-bottom:1px solid #e5e7eb; text-align:left; padding:10px; font-size:13px; }}
th {{ background:#eef5f0; }}
label {{ display:block; margin-top:12px; font-weight:800; }}
input,select {{ width:100%; padding:11px; margin-top:5px; border:1px solid #cbd5e1; border-radius:10px; font-size:14px; }}
.form-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
.badge {{ padding:5px 10px; border-radius:999px; font-weight:900; font-size:12px; }}
.CRITICO {{ background:#fee2e2; color:#991b1b; }}
.ATENCION {{ background:#fef3c7; color:#92400e; }}
.INFORMATIVO {{ background:#dbeafe; color:#1e40af; }}
.notice {{ background:#fff7ed; border-left:5px solid var(--fuego); padding:14px; border-radius:12px; margin-bottom:16px; }}
.ok {{ background:#ecfdf5; border-left:5px solid var(--verde); padding:14px; border-radius:12px; }}
.geo-help {{ background:#ecfeff; border-left:5px solid #0891b2; padding:12px; border-radius:12px; margin:12px 0; }}
.alert-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:16px; }}
.alert-card {{ border-radius:18px; padding:18px; background:white; box-shadow:0 6px 24px rgba(0,0,0,.08); border-left:8px solid #2563eb; }}
.alert-card.CRITICO {{ border-left-color:#991b1b; }}
.alert-card.ATENCION {{ border-left-color:#d97706; }}
.alert-card.INFORMATIVO {{ border-left-color:#2563eb; }}
.alert-title {{ display:flex; justify-content:space-between; gap:10px; align-items:center; margin-bottom:12px; }}
.alert-title h3 {{ margin:0; font-size:21px; }}
.alert-meta {{ display:grid; grid-template-columns:1fr 1fr; gap:8px 12px; margin:12px 0; font-size:14px; }}
.alert-meta div {{ background:#f8fafc; padding:9px; border-radius:10px; }}
.message-box {{ background:#f8fafc; border:1px solid #dbe3ea; border-radius:12px; padding:12px; margin-top:12px; font-size:13px; line-height:1.45; }}
.copy-button {{ background:#0f766e; padding:9px 12px; font-size:13px; margin-top:8px; }}
.user-grid,.zone-summary {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px; }}
.user-card,.zone-card {{ background:white; border-radius:16px; padding:18px; box-shadow:0 5px 20px rgba(0,0,0,.07); border-left:6px solid var(--verde); }}
.report-header {{ display:flex; justify-content:space-between; gap:20px; align-items:flex-start; border-bottom:3px solid #14532d; padding-bottom:16px; margin-bottom:18px; }}
.report-meta {{ background:#f8fafc; padding:14px; border-radius:12px; min-width:260px; font-size:13px; }}
.report-kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin:16px 0; }}
.report-kpi {{ background:#f8fafc; border:1px solid #e5e7eb; border-radius:14px; padding:14px; }}
.report-kpi strong {{ font-size:28px; display:block; }}
.print-actions,.quick-actions {{ display:flex; gap:10px; flex-wrap:wrap; margin:14px 0; }}
pre {{ white-space:pre-wrap; background:#111827; color:#e5e7eb; padding:14px; border-radius:8px; overflow:auto; }}

.map-toolbar {{
  position:absolute;
  z-index:1000;
  background:white;
  padding:12px;
  top:148px;
  right:16px;
  border-radius:16px;
  box-shadow:0 8px 28px rgba(0,0,0,.18);
  max-width:330px;
}}
.map-toolbar button {{
  padding:8px 10px;
  font-size:12px;
  margin:3px;
  border-radius:10px;
}}
.map-toolbar .lightbtn {{
  background:#e9f5ee;
  color:#14532d;
}}
.map-status {{
  font-size:12px;
  color:#334155;
  margin-top:8px;
  line-height:1.35;
}}
.clean-card {{
  border-left:6px solid var(--verde);
}}
.public-note {{
  background:#eefcf3;
  border-left:5px solid #15803d;
  padding:14px;
  border-radius:12px;
  margin-bottom:16px;
}}

@media(max-width:900px) {{ .hero,.form-grid {{ grid-template-columns:1fr; }} main {{ padding:18px; }} header,nav {{ padding-left:18px; padding-right:18px; }} }}
@media print {{ header, nav, .print-actions {{ display:none !important; }} body {{ background:white; }} main {{ padding:0; }} .card {{ box-shadow:none; border:0; padding:0; }} }}
</style>
</head>
<body>
<header><h1>CampoSeguro</h1><p>Alerta temprana informativa de focos de calor para zonas registradas</p></header>
<nav>
<a href="/">Inicio</a>
<a href="/mapa">Mapa</a>
<a href="/resumen">Resumen</a>
<a href="/monitor">Monitor</a>
<a href="/base-datos">Base de datos</a>
<a href="/reporte">Reporte</a>
<a href="/alertas">Alertas</a>
<a href="/zonas">Zonas</a>
<a href="/usuarios">Usuarios</a>
<a href="/correos">Correos</a>
<a href="/configuracion">Configuración</a>
<a href="/logout">Salir</a>
</nav>
<main>{body}</main>
<script>
function copiarTexto(id) {{
  const el = document.getElementById(id);
  if (!el) return;
  const text = el.innerText || el.textContent;
  navigator.clipboard.writeText(text).then(() => {{ alert("Mensaje copiado."); }}).catch(() => {{
    const area = document.createElement("textarea");
    area.value = text;
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    document.body.removeChild(area);
    alert("Mensaje copiado.");
  }});
}}
function usarUbicacionActual() {{
  if (!navigator.geolocation) {{
    alert("Este navegador no permite obtener ubicación.");
    return;
  }}
  const btn = document.getElementById("geo-btn");
  if (btn) btn.innerText = "Buscando ubicación...";
  navigator.geolocation.getCurrentPosition(
    (pos) => {{
      const lat = pos.coords.latitude.toFixed(7);
      const lon = pos.coords.longitude.toFixed(7);
      const latInput = document.querySelector("input[name='latitud']");
      const lonInput = document.querySelector("input[name='longitud']");
      if (latInput) latInput.value = lat;
      if (lonInput) lonInput.value = lon;
      if (btn) btn.innerText = "Usar mi ubicación actual";
      alert("Ubicación cargada: " + lat + ", " + lon);
    }},
    () => {{
      if (btn) btn.innerText = "Usar mi ubicación actual";
      alert("No se pudo obtener la ubicación. Revisa permisos del navegador.");
    }},
    {{ enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }}
  );
}}
</script>
</body>
</html>"""


def error_page(exc):
    return HTMLResponse(layout("Error", f"<div class='card'><h2>Error</h2><pre>{esc(traceback.format_exc())}</pre></div>"), status_code=500)


@app.on_event("startup")
def startup():
    init_db()
    seed_demo_data()
    start_background_monitor()


def stats():
    conn = get_conn()
    data = {
        "usuarios": conn.execute("SELECT COUNT(*) FROM usuarios WHERE activo=1").fetchone()[0],
        "zonas": conn.execute("SELECT COUNT(*) FROM zonas WHERE activa=1").fetchone()[0],
        "focos": conn.execute("SELECT COUNT(*) FROM focos").fetchone()[0],
        "alertas": conn.execute("SELECT COUNT(*) FROM alertas").fetchone()[0],
        "criticas": conn.execute("SELECT COUNT(*) FROM alertas WHERE nivel='CRITICO'").fetchone()[0],
        "atencion": conn.execute("SELECT COUNT(*) FROM alertas WHERE nivel='ATENCION'").fetchone()[0],
        "informativas": conn.execute("SELECT COUNT(*) FROM alertas WHERE nivel='INFORMATIVO'").fetchone()[0],
    }
    conn.close()
    return data




def radio_options_html(selected=None):
    selected_val = float(selected if selected is not None else DEFAULT_ZONE_RADIUS_KM)
    values = [1, 3, 5, 10, 15, 20, 25, 30, 50, 75, 100]
    options = ""
    for v in values:
        if float(v) < CLIENT_MIN_RADIUS_KM or float(v) > max(CLIENT_MAX_RADIUS_KM, DEFAULT_ZONE_RADIUS_KM):
            continue
        sel = "selected" if abs(float(v) - selected_val) < 0.001 else ""
        options += f'<option value="{v}" {sel}>{v} km</option>'
    if str(selected_val).rstrip("0").rstrip(".") not in [str(v) for v in values]:
        options += f'<option value="{selected_val}" selected>{selected_val:g} km</option>'
    return options


def clamp_radio_cliente(radio):
    try:
        r = float(radio)
    except Exception:
        r = DEFAULT_ZONE_RADIUS_KM
    return max(CLIENT_MIN_RADIUS_KM, min(CLIENT_MAX_RADIUS_KM, r))



def layout_cliente(title, body):
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>{esc(title)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {{
  --verde-oscuro:#0f3023; --verde:#1f6f43; --verde-suave:#e9f5ee;
  --gris:#f4f6f7; --texto:#142026; --fuego:#f97316; --rojo:#dc2626; --azul:#2563eb;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:Inter,Arial,sans-serif; background:var(--gris); color:var(--texto); }}
header {{ background:linear-gradient(135deg,#0f3023,#1f6f43); color:white; padding:24px 28px 18px; }}
header h1 {{ margin:0; font-size:30px; letter-spacing:-.5px; }}
header p {{ margin:6px 0 0; opacity:.92; }}
nav {{ background:#184a34; padding:12px 28px; display:flex; gap:18px; flex-wrap:wrap; }}
nav a {{ color:white; text-decoration:none; font-weight:800; }}
main {{ padding:24px 28px; }}
.card {{ background:white; border-radius:18px; padding:22px; margin-bottom:18px; box-shadow:0 6px 24px rgba(0,0,0,.08); }}
.hero {{ background:white; border-radius:20px; padding:28px; margin-bottom:20px; box-shadow:0 8px 30px rgba(0,0,0,.08); }}
.hero h2 {{ margin:0 0 10px; font-size:30px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:16px; }}
.metric-label {{ color:#52616a; font-weight:800; font-size:14px; }}
.metric {{ font-size:34px; font-weight:900; margin-top:6px; }}
.button {{ background:var(--verde); color:white; border:0; border-radius:12px; padding:12px 18px; font-weight:900; cursor:pointer; text-decoration:none; display:inline-block; }}
.button.light {{ background:var(--verde-suave); color:#14532d; }}
table {{ border-collapse:collapse; width:100%; background:white; }}
th,td {{ border-bottom:1px solid #e5e7eb; text-align:left; padding:10px; font-size:13px; }}
th {{ background:#eef5f0; }}
.badge {{ padding:5px 10px; border-radius:999px; font-weight:900; font-size:12px; }}
.CRITICO {{ background:#fee2e2; color:#991b1b; }}
.ATENCION {{ background:#fef3c7; color:#92400e; }}
.INFORMATIVO {{ background:#dbeafe; color:#1e40af; }}
.notice {{ background:#fff7ed; border-left:5px solid var(--fuego); padding:14px; border-radius:12px; margin-bottom:16px; }}
.alert-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:16px; }}
.alert-card {{ border-radius:18px; padding:18px; background:white; box-shadow:0 6px 24px rgba(0,0,0,.08); border-left:8px solid #2563eb; }}
.alert-card.CRITICO {{ border-left-color:#991b1b; }}
.alert-card.ATENCION {{ border-left-color:#d97706; }}
.alert-card.INFORMATIVO {{ border-left-color:#2563eb; }}
.alert-title {{ display:flex; justify-content:space-between; gap:10px; align-items:center; margin-bottom:12px; }}
.alert-title h3 {{ margin:0; font-size:21px; }}
.alert-meta {{ display:grid; grid-template-columns:1fr 1fr; gap:8px 12px; margin:12px 0; font-size:14px; }}
.alert-meta div {{ background:#f8fafc; padding:9px; border-radius:10px; }}
.message-box {{ background:#f8fafc; border:1px solid #dbe3ea; border-radius:12px; padding:12px; margin-top:12px; font-size:13px; line-height:1.45; }}
@media(max-width:900px) {{ main {{ padding:16px; }} header,nav {{ padding-left:16px; padding-right:16px; }} }}
</style>
</head>
<body>
<header><h1>CampoSeguro</h1><p>Vista cliente: seguimiento informativo de focos de calor</p></header>
<nav>
<a href="/cliente">Inicio</a>
<a href="/cliente/mapa">Mapa</a>
<a href="/cliente/zonas">Mis zonas</a>
<a href="/cliente/alertas">Mis alertas</a>
<a href="/cliente/reporte">Reporte</a>
<a href="/logout">Salir</a>
</nav>
<main>{body}</main>
</body>
</html>"""


def cliente_metricas():
    conn = get_conn()
    zonas = conn.execute("SELECT COUNT(*) AS n FROM zonas WHERE activa=1").fetchone()["n"]
    focos = conn.execute("SELECT COUNT(*) AS n FROM focos").fetchone()["n"]
    alertas = conn.execute("SELECT COUNT(*) AS n FROM alertas").fetchone()["n"]
    criticas = conn.execute("SELECT COUNT(*) AS n FROM alertas WHERE nivel='CRITICO'").fetchone()["n"]
    conn.close()
    return zonas, focos, alertas, criticas


@app.get("/cliente", response_class=HTMLResponse)
def cliente_inicio():
    zonas, focos, alertas, criticas = cliente_metricas()
    body = f"""
    <section class="hero">
      <h2>Panel de seguimiento</h2>
      <p>Consulta el mapa, revisa alertas registradas y descarga información operativa de manera simple. Esta vista es solo de lectura.</p>
      <p>
        <a class="button" href="/cliente/mapa">Ver mapa</a>
        <a class="button light" href="/cliente/zonas">Ajustar radios</a>
        <a class="button light" href="/cliente/alertas">Ver alertas</a>
        <a class="button light" href="/cliente/reporte">Ver reporte</a>
      </p>
    </section>
    <section class="grid">
      <div class="card"><div class="metric-label">Zonas monitoreadas</div><div class="metric">{zonas}</div></div>
      <div class="card"><div class="metric-label">Focos FIRMS</div><div class="metric">{focos}</div></div>
      <div class="card"><div class="metric-label">Alertas registradas</div><div class="metric">{alertas}</div></div>
      <div class="card"><div class="metric-label">Críticas</div><div class="metric">{criticas}</div></div>
    </section>
    <div class="notice">CampoSeguro es una herramienta informativa. No reemplaza verificación en campo ni sistemas oficiales de emergencia.</div>
    """
    return layout_cliente("CampoSeguro | Cliente", body)



@app.get("/cliente/zonas", response_class=HTMLResponse)
def cliente_zonas():
    conn = get_conn()
    zonas = rows_to_dicts(conn.execute("""
        SELECT z.*, u.nombre AS usuario_nombre
        FROM zonas z LEFT JOIN usuarios u ON u.id=z.usuario_id
        WHERE z.activa=1
        ORDER BY z.nombre_zona ASC
    """).fetchall())
    conn.close()

    rows = ""
    for z in zonas:
        rows += f"""
        <tr>
          <td><strong>{esc(z['nombre_zona'])}</strong><br><small>{esc(z['municipio'] or '')}</small></td>
          <td>{esc(z['radio_km'])} km</td>
          <td>
            <form method="post" action="/cliente/zonas/radio" style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
              <input type="hidden" name="zona_id" value="{esc(z['id'])}">
              <select name="radio_km">{radio_options_html(z['radio_km'])}</select>
              <button class="button" type="submit">Guardar radio</button>
            </form>
          </td>
        </tr>
        """

    body = f"""
    <div class="card">
      <h2>Mis zonas</h2>
      <p>Ajusta el radio de alerta de cada zona. Un radio más corto reduce alertas lejanas y evita saturar el correo.</p>
      <div class="notice">
        Recomendación inicial: <strong>{esc(DEFAULT_ZONE_RADIUS_KM)} km</strong>. Para predios pequeños: 3 a 10 km. Para municipios o áreas grandes: 15 a 30 km.
      </div>
      <table>
        <tr><th>Zona</th><th>Radio actual</th><th>Nuevo radio</th></tr>
        {rows}
      </table>
    </div>
    """
    return layout_cliente("CampoSeguro | Mis zonas", body)


@app.post("/cliente/zonas/radio")
def cliente_zona_radio(zona_id: int = Form(...), radio_km: float = Form(...)):
    radio = clamp_radio_cliente(radio_km)
    conn = get_conn()
    conn.execute("UPDATE zonas SET radio_km=? WHERE id=? AND activa=1", (radio, zona_id))
    conn.commit()
    conn.close()
    recalcular_alertas_existentes()
    return RedirectResponse("/cliente/zonas", status_code=303)



@app.get("/cliente/mapa", response_class=HTMLResponse)
def cliente_mapa():
    try:
        conn = get_conn()
        zonas = rows_to_dicts(conn.execute("""
            SELECT z.*, u.nombre AS usuario_nombre
            FROM zonas z LEFT JOIN usuarios u ON u.id=z.usuario_id
            WHERE z.activa=1
        """).fetchall())
        focos = rows_to_dicts(conn.execute("""
            SELECT * FROM focos
            ORDER BY acq_date DESC, acq_time DESC
            LIMIT 10000
        """).fetchall())
        total_alertas = conn.execute("SELECT COUNT(*) AS n FROM alertas").fetchone()["n"]
        conn.close()

        body = f"""
        <style>
        main {{ padding:0; }}
        #map {{ height:calc(100vh - 126px); width:100%; }}
        .panel {{
          position:absolute; z-index:1000; background:white; padding:14px 16px;
          top:148px; left:16px; border-radius:16px; box-shadow:0 8px 28px rgba(0,0,0,.2);
          max-width:320px; font-size:15px;
        }}
        .legend-dot {{ display:inline-block; width:12px; height:12px; border-radius:50%; margin-right:6px; }}
        .legend-line {{ display:inline-block; width:18px; height:12px; border:3px solid #2563eb; border-radius:50%; margin-right:6px; vertical-align:middle; }}
        .active-mode {{ background:#dcfce7; color:#14532d; padding:7px 9px; border-radius:9px; display:inline-block; margin-top:8px; font-weight:900; }}
        .map-toolbar {{
          position:absolute; z-index:1000; background:white; padding:14px; top:148px; right:16px;
          border-radius:16px; box-shadow:0 8px 28px rgba(0,0,0,.18); max-width:300px;
        }}
        .map-toolbar button {{
          padding:10px 14px; font-size:14px; margin:4px; border-radius:12px; border:0;
          font-weight:900; cursor:pointer; background:#e9f5ee; color:#14532d;
        }}
        .map-status {{ font-size:13px; color:#334155; margin-top:10px; line-height:1.35; }}
        </style>

        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />

        <div class="panel">
          <strong>CampoSeguro</strong><br>
          Área operativa: Bolivia<br>
          Zonas: {len(zonas)}<br>
          Focos FIRMS: {len(focos)}<br>
          Alertas registradas: {total_alertas}<hr>
          <span class="legend-line"></span>Zona monitoreada<br>
          <span class="legend-dot" style="background:#f97316"></span>Foco MODIS<br>
          <span class="legend-dot" style="background:#dc2626"></span>Foco VIIRS<br>
          <div id="mode-label" class="active-mode">Todo</div>
        </div>

        <div class="map-toolbar">
          <strong>Vista del mapa</strong><br>
          <button onclick="verZonas()">Zonas</button>
          <button onclick="verFocos()">Focos</button>
          <button onclick="verTodo()">Todo</button>
          <div class="map-status">Mapa simple para consulta. Las alertas están en la pestaña Mis alertas.</div>
        </div>

        <div id="map"></div>

        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script>
        const zonas = {json.dumps(zonas)};
        const focos = {json.dumps(focos)};

        const canvasRenderer = L.canvas({{ padding: 0.5 }});
        const map = L.map('map').setView([-16.6, -64.5], 6);

        L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
          maxZoom:19,
          attribution:'&copy; OpenStreetMap'
        }}).addTo(map);

        map.createPane('focosPane');
        map.getPane('focosPane').style.zIndex = 420;
        map.createPane('zonasPane');
        map.getPane('zonasPane').style.zIndex = 520;

        const layerZonas = L.layerGroup().addTo(map);
        const layerFocos = L.layerGroup().addTo(map);

        function focoColor(fuente) {{
          return (fuente || '').includes('VIIRS') ? '#dc2626' : '#f97316';
        }}

        function setMode(text) {{
          const el = document.getElementById('mode-label');
          if (el) el.innerText = text;
        }}

        zonas.forEach(z => {{
          L.circle([z.latitud, z.longitud], {{
            pane:'zonasPane',
            radius:z.radio_km*1000,
            color:'#2563eb',
            weight:4,
            fillColor:'#2563eb',
            fillOpacity:0.05
          }})
          .addTo(layerZonas)
          .bindPopup(`<b>Zona monitoreada</b><br>${{z.nombre_zona}}<br><b>Municipio:</b> ${{z.municipio || ''}}<br><b>Radio:</b> ${{z.radio_km}} km`);

          L.circleMarker([z.latitud, z.longitud], {{
            pane:'zonasPane',
            radius:7,
            color:'#1d4ed8',
            fillColor:'#1d4ed8',
            fillOpacity:0.9,
            weight:2
          }})
          .addTo(layerZonas)
          .bindPopup(`<b>Centro de zona</b><br>${{z.nombre_zona}}`);
        }});

        focos.forEach(f => {{
          const color = focoColor(f.fuente);
          L.circleMarker([f.latitude, f.longitude], {{
            renderer: canvasRenderer,
            pane:'focosPane',
            radius:4,
            color:color,
            fillColor:color,
            fillOpacity:0.70,
            opacity:0.85,
            weight:1
          }})
          .addTo(layerFocos)
          .bindPopup(`<b>Foco de calor</b><br>${{f.fuente}}<br>${{f.acq_date}} ${{f.acq_time}}<br>Satélite: ${{f.satellite || ''}}<br>FRP: ${{f.frp || ''}}`);
        }});

        function addIfMissing(layer) {{ if (!map.hasLayer(layer)) map.addLayer(layer); }}
        function removeIfPresent(layer) {{ if (map.hasLayer(layer)) map.removeLayer(layer); }}

        function verZonas() {{
          addIfMissing(layerZonas);
          removeIfPresent(layerFocos);
          setMode('Zonas');
        }}

        function verFocos() {{
          removeIfPresent(layerZonas);
          addIfMissing(layerFocos);
          setMode('Focos');
        }}

        function verTodo() {{
          addIfMissing(layerZonas);
          addIfMissing(layerFocos);
          setMode('Todo');
        }}

        verTodo();
        </script>
        """
        return layout_cliente("CampoSeguro | Mapa cliente", body)
    except Exception as exc:
        return error_page(exc)


@app.get("/cliente/alertas", response_class=HTMLResponse)
def cliente_alertas():
    conn = get_conn()
    alertas = rows_to_dicts(conn.execute("""
        SELECT a.*, z.nombre_zona, z.municipio, f.fuente, f.acq_date, f.acq_time
        FROM alertas a
        JOIN zonas z ON z.id=a.zona_id
        JOIN focos f ON f.id=a.foco_id
        ORDER BY CASE WHEN a.nivel='CRITICO' THEN 1 WHEN a.nivel='ATENCION' THEN 2 ELSE 3 END,
                 a.distancia_km ASC
        LIMIT 100
    """).fetchall())
    conn.close()

    cards = ""
    if not alertas:
        cards = '<div class="card">No hay alertas registradas en este momento.</div>'
    else:
        for i, a in enumerate(alertas):
            msg = esc(mensaje_alerta(a))
            cards += f"""
            <div class="alert-card {esc(a['nivel'])}">
              <div class="alert-title">
                <h3>{esc(a['nombre_zona'])}</h3>
                <span class="badge {esc(a['nivel'])}">{esc(a['nivel'])}</span>
              </div>
              <div class="alert-meta">
                <div><strong>Municipio</strong><br>{esc(a['municipio'])}</div>
                <div><strong>Distancia</strong><br>{esc(a['distancia_km'])} km</div>
                <div><strong>Fuente</strong><br>{esc(a['fuente'])}</div>
                <div><strong>Fecha</strong><br>{esc(a['acq_date'])} {esc(a['acq_time'])}</div>
              </div>
              <div class="message-box">{msg}</div>
            </div>
            """

    body = f"""
    <div class="card">
      <h2>Mis alertas</h2>
      <p>Alertas informativas generadas por cercanía de focos de calor a zonas monitoreadas.</p>
    </div>
    <div class="alert-grid">{cards}</div>
    """
    return layout_cliente("CampoSeguro | Mis alertas", body)


@app.get("/cliente/reporte", response_class=HTMLResponse)
def cliente_reporte():
    conn = get_conn()
    k = {
        "zonas": conn.execute("SELECT COUNT(*) AS n FROM zonas WHERE activa=1").fetchone()["n"],
        "focos": conn.execute("SELECT COUNT(*) AS n FROM focos").fetchone()["n"],
        "alertas": conn.execute("SELECT COUNT(*) AS n FROM alertas").fetchone()["n"],
        "criticas": conn.execute("SELECT COUNT(*) AS n FROM alertas WHERE nivel='CRITICO'").fetchone()["n"],
    }
    resumen = rows_to_dicts(conn.execute("""
        SELECT z.nombre_zona, z.municipio,
               COUNT(a.id) AS alertas,
               MIN(a.distancia_km) AS distancia_minima,
               MAX(CASE WHEN a.nivel='CRITICO' THEN 3 WHEN a.nivel='ATENCION' THEN 2 ELSE 1 END) AS prioridad
        FROM zonas z
        LEFT JOIN alertas a ON a.zona_id=z.id
        WHERE z.activa=1
        GROUP BY z.id
        ORDER BY alertas DESC, z.nombre_zona ASC
    """).fetchall())
    conn.close()

    rows = ""
    for r in resumen:
        prioridad = r["prioridad"] or 0
        nivel = "CRITICO" if prioridad == 3 else ("ATENCION" if prioridad == 2 else ("INFORMATIVO" if prioridad == 1 else "SIN ALERTA"))
        distancia = "" if r["distancia_minima"] is None else f"{float(r['distancia_minima']):.2f} km"
        badge = f'<span class="badge {nivel}">{nivel}</span>' if nivel != "SIN ALERTA" else "SIN ALERTA"
        rows += f"""
        <tr>
          <td>{esc(r['nombre_zona'])}</td>
          <td>{esc(r['municipio'])}</td>
          <td>{esc(r['alertas'])}</td>
          <td>{badge}</td>
          <td>{esc(distancia)}</td>
        </tr>
        """

    body = f"""
    <div class="card">
      <h2>Reporte CampoSeguro</h2>
      <p>Resumen informativo para seguimiento preventivo.</p>
    </div>
    <section class="grid">
      <div class="card"><div class="metric-label">Zonas</div><div class="metric">{k['zonas']}</div></div>
      <div class="card"><div class="metric-label">Focos</div><div class="metric">{k['focos']}</div></div>
      <div class="card"><div class="metric-label">Alertas</div><div class="metric">{k['alertas']}</div></div>
      <div class="card"><div class="metric-label">Críticas</div><div class="metric">{k['criticas']}</div></div>
    </section>
    <div class="card">
      <h3>Resumen por zona</h3>
      <table>
        <tr><th>Zona</th><th>Municipio</th><th>Alertas</th><th>Nivel máximo</th><th>Distancia mínima</th></tr>
        {rows}
      </table>
    </div>
    <div class="notice">CampoSeguro es una herramienta informativa. No reemplaza verificación en campo ni sistemas oficiales.</div>
    """
    return layout_cliente("CampoSeguro | Reporte cliente", body)





def render_monitor_status_card(status):
    last_result = status.get("last_result") or {}
    correos_proc = status.get("correos_procesados") or {}
    success = status.get("last_success")
    success_txt = "Sin ejecución todavía" if success is None else ("Correcto" if success else "Con error")
    success_class = "ok" if success else ("notice" if success is None else "bad")

    return f"""
    <div class="card">
      <h2>Monitoreo automático</h2>
      <p><strong>Estado:</strong> {esc(success_txt)}</p>
      <p><strong>Activo:</strong> {esc("Sí" if status.get("enabled") else "No")}</p>
      <p><strong>Ejecutándose ahora:</strong> {esc("Sí" if status.get("running") else "No")}</p>
      <p><strong>Intervalo:</strong> cada {esc(status.get("interval_minutes"))} minutos</p>
      <p><strong>Última ejecución UTC:</strong> {esc(status.get("last_run_utc") or "Pendiente")}</p>
      <p><strong>Último disparador:</strong> {esc(status.get("last_trigger") or "Ninguno")}</p>
      <p><strong>Próxima referencia:</strong> {esc(status.get("next_run_hint") or "Pendiente")}</p>
      <hr>
      <p><strong>Focos descargados:</strong> {esc(last_result.get("focos_descargados", 0))}</p>
      <p><strong>Focos nuevos guardados:</strong> {esc(last_result.get("focos_nuevos_guardados", 0))}</p>
      <p><strong>Alertas recalculadas:</strong> {esc(last_result.get("alertas_totales", 0))}</p>
      <p><strong>Correos preparados:</strong> {esc(status.get("correos_preparados", 0))}</p>
      <p><strong>Correos procesados:</strong> {esc(correos_proc.get("procesados", 0))} |
         enviados: {esc(correos_proc.get("enviados", 0))} |
         outbox: {esc(correos_proc.get("outbox", 0))} |
         errores: {esc(correos_proc.get("errores", 0))}</p>
      <p><strong>SMTP activo:</strong> {esc("Sí" if status.get("smtp_active") else "No")}</p>
    </div>
    """



@app.get("/base-datos", response_class=HTMLResponse)
def base_datos_panel():
    try:
        status = db_status()
        conn = get_conn()
        counts = {
            "usuarios": conn.execute("SELECT COUNT(*) AS n FROM usuarios").fetchone()["n"],
            "zonas": conn.execute("SELECT COUNT(*) AS n FROM zonas").fetchone()["n"],
            "focos": conn.execute("SELECT COUNT(*) AS n FROM focos").fetchone()["n"],
            "alertas": conn.execute("SELECT COUNT(*) AS n FROM alertas").fetchone()["n"],
            "correos": conn.execute("SELECT COUNT(*) AS n FROM correos_alerta").fetchone()["n"],
        }
        conn.close()

        persistent_text = "Sí, PostgreSQL externo" if status["persistent"] else "No, SQLite local"
        notice = "" if status["persistent"] else """
        <div class="notice">
          Esta plataforma todavía usa SQLite local. Para persistencia real en Render debes agregar DATABASE_URL de Neon o Supabase y redeplegar.
        </div>
        """
        body = f"""
        <div class="card">
          <h2>Base de datos</h2>
          <p><strong>Motor actual:</strong> {esc(status['backend'])}</p>
          <p><strong>Persistente:</strong> {esc(persistent_text)}</p>
          <p><strong>DATABASE_URL configurada:</strong> {esc('Sí' if status['database_url_configured'] else 'No')}</p>
          {notice}
        </div>
        <section class="grid">
          <div class="card"><div class="metric-label">Usuarios</div><div class="metric">{counts['usuarios']}</div></div>
          <div class="card"><div class="metric-label">Zonas</div><div class="metric">{counts['zonas']}</div></div>
          <div class="card"><div class="metric-label">Focos</div><div class="metric">{counts['focos']}</div></div>
          <div class="card"><div class="metric-label">Alertas</div><div class="metric">{counts['alertas']}</div></div>
          <div class="card"><div class="metric-label">Correos</div><div class="metric">{counts['correos']}</div></div>
        </section>
        <div class="card">
          <h3>Qué significa</h3>
          <p>Con PostgreSQL externo, usuarios, zonas, radios, focos, alertas y correos permanecen aunque Render reinicie.</p>
          <p><a class="button light" href="/monitor">Ver monitor</a> <a class="button light" href="/configuracion">Ver configuración</a></p>
        </div>
        """
        return layout("Base de datos", body)
    except Exception as exc:
        return error_page(exc)


@app.get("/monitor", response_class=HTMLResponse)
def monitor_panel():
    status = get_auto_monitor_status()
    secret_status = "Configurado" if MONITOR_SECRET else "No configurado"
    body = f"""
    {render_monitor_status_card(status)}
    <div class="card">
      <h3>Acciones</h3>
      <form method="post" action="/monitor/ejecutar" style="display:inline-block;">
        <button type="submit">Ejecutar monitoreo ahora</button>
      </form>
      <a class="button light" href="/correos">Ver correos</a>
      <a class="button light" href="/reporte">Ver reporte</a>
    </div>
    <div class="card">
      <h3>Configuración automática</h3>
      <p><strong>AUTO_MONITOR_ENABLED:</strong> {esc(AUTO_MONITOR_ENABLED)}</p>
      <p><strong>AUTO_MONITOR_INTERVAL_MINUTES:</strong> {esc(AUTO_MONITOR_INTERVAL_MINUTES)}</p>
      <p><strong>AUTO_MONITOR_RUN_ON_STARTUP:</strong> {esc(AUTO_MONITOR_RUN_ON_STARTUP)}</p>
      <p><strong>AUTO_MONITOR_START_DELAY_SECONDS:</strong> {esc(AUTO_MONITOR_START_DELAY_SECONDS)}</p>
      <p><strong>MONITOR_SECRET:</strong> {esc(secret_status)}</p>
      <p class="notice">En Render gratis, si el servicio se duerme, el monitor interno se pausa. Para 24/7 barato, se puede usar luego un cron externo que llame a /cron/monitor con token secreto.</p>
    </div>
    """
    return layout("Monitor automático", body)


@app.post("/monitor/ejecutar", response_class=HTMLResponse)
def monitor_ejecutar():
    status = run_monitor_once(trigger="admin_button")
    body = f"""
    {render_monitor_status_card(status)}
    <div class="card">
      <p><a class="button" href="/monitor">Volver al monitor</a>
      <a class="button light" href="/mapa">Ver mapa</a>
      <a class="button light" href="/alertas">Ver alertas</a></p>
    </div>
    """
    return layout("Monitor ejecutado", body)


@app.get("/cron/monitor")
def cron_monitor(token: str = ""):
    if not MONITOR_SECRET or token != MONITOR_SECRET:
        return {"ok": False, "error": "token inválido o MONITOR_SECRET no configurado"}
    status = run_monitor_once(trigger="external_cron")
    return {
        "ok": bool(status.get("last_success")),
        "running": status.get("running"),
        "last_run_utc": status.get("last_run_utc"),
        "focos_descargados": (status.get("last_result") or {}).get("focos_descargados", 0),
        "focos_nuevos_guardados": (status.get("last_result") or {}).get("focos_nuevos_guardados", 0),
        "alertas_totales": (status.get("last_result") or {}).get("alertas_totales", 0),
        "correos_preparados": status.get("correos_preparados", 0),
        "correos_procesados": status.get("correos_procesados", {}),
        "error": status.get("last_error"),
    }




@app.get("/", response_class=HTMLResponse)
def inicio():
    try:
        s = stats()
        key_status = "Configurada" if FIRMS_MAP_KEY and FIRMS_MAP_KEY != "coloca_aqui_tu_map_key" else "Falta configurar"
        body = f"""
        <section class="hero">
          <div>
            <h2>Monitoreo de fuego cercano</h2>
            <p>Registra usuarios y zonas de interés. CampoSeguro consulta FIRMS y prioriza alertas registradas para seguimiento preventivo.</p>
            <form method="post" action="/actualizar" style="display:inline-block;"><button type="submit">Actualizar monitoreo</button></form>
            <a class="button light" href="/mapa">Ver mapa</a>
            <div class="quick-actions">
              <a class="button light" href="/usuarios">Usuarios</a>
              <a class="button light" href="/zonas">Zonas</a>
              <a class="button light" href="/monitor">Monitor automático</a>
              <a class="button light" href="/reporte">Reporte operativo</a>
              <a class="button light" href="/correos">Correos</a>
            </div>
          </div>
          <div class="ok">
            <strong>Estado del sistema</strong><br>
            Llave FIRMS: {esc(key_status)}<br>
            Región API: Sudamérica / South_America<br>
            Área operativa: Bolivia<br>
            Evaluación de alertas: últimas {esc(ALERT_EVALUATION_HOURS)} horas<br>
            Monitor automático: {esc("Activo" if AUTO_MONITOR_ENABLED else "Desactivado")} / cada {esc(AUTO_MONITOR_INTERVAL_MINUTES)} min<br>Base de datos: {esc(DB_BACKEND)}
          </div>
        </section>

        <section class="grid">
          <div class="card"><div class="metric-label">Usuarios activos</div><div class="metric">{s['usuarios']}</div></div>
          <div class="card"><div class="metric-label">Zonas activas</div><div class="metric">{s['zonas']}</div></div>
          <div class="card"><div class="metric-label">Focos FIRMS</div><div class="metric">{s['focos']}</div></div>
          <div class="card"><div class="metric-label">Alertas</div><div class="metric">{s['alertas']}</div></div>
          <div class="card"><div class="metric-label">Críticas</div><div class="metric">{s['criticas']}</div></div>
        </section>

        <div class="card">
          <h2>Distribución de alertas</h2>
          <p>
            <span class="badge CRITICO">Críticas: {s['criticas']}</span>
            <span class="badge ATENCION">Atención: {s['atencion']}</span>
            <span class="badge INFORMATIVO">Informativas: {s['informativas']}</span>
          </p>
          <p class="notice">CampoSeguro es informativo. No reemplaza verificación en campo ni sistemas oficiales.</p>
        </div>
        """
        return layout("Inicio", body)
    except Exception as exc:
        return error_page(exc)


@app.post("/actualizar", response_class=HTMLResponse)
def actualizar():
    try:
        r = run_monitoring()
        nuevos_correos = preparar_correos_pendientes()
        detail = ""
        rows = ""
        for rep in r["reports"]:
            if rep["error"] or rep["message"]:
                rows += f"<tr><td>{esc(rep['source'])}</td><td>{esc(rep.get('url',''))}</td><td>{esc(rep['error'] or rep['message'])}</td></tr>"
        if rows:
            detail = f"<div class='card'><h3>Mensajes técnicos</h3><table><tr><th>Fuente</th><th>URL</th><th>Mensaje</th></tr>{rows}</table></div>"

        body = f"""
        <div class="card">
          <h2>Monitoreo actualizado</h2>
          <p><strong>Región API:</strong> {esc(r.get('strategy_info', {}).get('api_region', 'South_America'))}</p>
          <p><strong>Área usada:</strong> {esc(r.get('strategy_info', {}).get('selected_area', ''))}</p>
          <p><strong>BBOX usado:</strong> {esc(r.get('strategy_info', {}).get('selected_bbox', ''))}</p>
          <p><strong>Focos descargados:</strong> {esc(r['focos_descargados'])}</p>
          <p><strong>Focos nuevos guardados:</strong> {esc(r['focos_nuevos_guardados'])}</p>
          <p><strong>Alertas totales recalculadas:</strong> {esc(r['alertas_totales'])}</p>
          <p><strong>Correos preparados:</strong> {esc(nuevos_correos)}</p>
          <p><strong>Fecha UTC:</strong> {esc(r['fecha_utc'])}</p>
          <p><a class="button" href="/mapa">Ver mapa</a> <a class="button light" href="/alertas">Ver alertas</a> <a class="button light" href="/correos">Ver correos</a> <a class="button light" href="/monitor">Ver monitor</a></p>
        </div>{detail}
        """
        return layout("Resultado", body)
    except Exception as exc:
        return error_page(exc)


@app.post("/limpiar")
def limpiar():
    clear_data()
    return RedirectResponse("/", status_code=303)




def distancia_km_simple(lat1, lon1, lat2, lon2):
    r = 6371.0088
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def focos_contexto_por_zonas(focos, zonas, margen_km=60):
    contexto = []
    vistos = set()

    for f in focos:
        mejor_dist = None
        mejor_zona = None

        for z in zonas:
            try:
                dist = distancia_km_simple(z["latitud"], z["longitud"], f["latitude"], f["longitude"])
                radio_contexto = float(z["radio_km"]) + float(margen_km)
                if dist <= radio_contexto and (mejor_dist is None or dist < mejor_dist):
                    mejor_dist = dist
                    mejor_zona = z
            except Exception:
                continue

        if mejor_zona:
            key = f.get("id") or f'{f.get("fuente")}_{f.get("latitude")}_{f.get("longitude")}_{f.get("acq_date")}_{f.get("acq_time")}'
            if key in vistos:
                continue
            vistos.add(key)
            row = dict(f)
            row["distancia_zona_km"] = round(mejor_dist, 2)
            row["zona_cercana"] = mejor_zona.get("nombre_zona", "")
            contexto.append(row)

    return contexto


@app.get("/mapa", response_class=HTMLResponse)
def mapa():
    try:
        conn = get_conn()
        zonas = rows_to_dicts(conn.execute("""
            SELECT z.*, u.nombre AS usuario_nombre
            FROM zonas z LEFT JOIN usuarios u ON u.id=z.usuario_id
            WHERE z.activa=1
        """).fetchall())

        focos = rows_to_dicts(conn.execute("""
            SELECT * FROM focos
            ORDER BY acq_date DESC, acq_time DESC
            LIMIT 10000
        """).fetchall())

        total_alertas = conn.execute("SELECT COUNT(*) AS n FROM alertas").fetchone()["n"]
        conn.close()

        body = f"""
        <style>
        main {{ padding:0; }}
        #map {{ height:calc(100vh - 126px); width:100%; }}
        .panel {{
          position:absolute;
          z-index:1000;
          background:white;
          padding:14px 16px;
          top:148px;
          left:16px;
          border-radius:16px;
          box-shadow:0 8px 28px rgba(0,0,0,.2);
          max-width:330px;
          font-size:15px;
        }}
        .legend-dot {{
          display:inline-block;
          width:12px;
          height:12px;
          border-radius:50%;
          margin-right:6px;
        }}
        .legend-line {{
          display:inline-block;
          width:18px;
          height:12px;
          border:3px solid #2563eb;
          border-radius:50%;
          margin-right:6px;
          vertical-align:middle;
        }}
        .active-mode {{
          background:#dcfce7;
          color:#14532d;
          padding:7px 9px;
          border-radius:9px;
          display:inline-block;
          margin-top:8px;
          font-weight:900;
        }}
        .map-toolbar {{
          position:absolute;
          z-index:1000;
          background:white;
          padding:14px;
          top:148px;
          right:16px;
          border-radius:16px;
          box-shadow:0 8px 28px rgba(0,0,0,.18);
          max-width:300px;
        }}
        .map-toolbar button {{
          padding:10px 14px;
          font-size:14px;
          margin:4px;
          border-radius:12px;
          border:0;
          font-weight:900;
          cursor:pointer;
          background:#e9f5ee;
          color:#14532d;
        }}
        .map-status {{
          font-size:13px;
          color:#334155;
          margin-top:10px;
          line-height:1.35;
        }}
        </style>

        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />

        <div class="panel">
          <strong>CampoSeguro</strong><br>
          Área operativa: Bolivia<br>
          Zonas: {len(zonas)}<br>
          Focos FIRMS: {len(focos)}<br>
          Alertas registradas: {total_alertas}<hr>
          <span class="legend-line"></span>Zona monitoreada<br>
          <span class="legend-dot" style="background:#f97316"></span>Foco MODIS<br>
          <span class="legend-dot" style="background:#dc2626"></span>Foco VIIRS<br>
          <div id="mode-label" class="active-mode">Todo</div>
        </div>

        <div class="map-toolbar">
          <strong>Vista del mapa</strong><br>
          <button onclick="verZonas()">Zonas</button>
          <button onclick="verFocos()">Focos</button>
          <button onclick="verTodo()">Todo</button>
          <div class="map-status">
            Mapa simplificado: las alertas se revisan en las pestañas Alertas y Reporte. Aquí se muestra el contexto territorial.
          </div>
        </div>

        <div id="map"></div>

        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script>
        const zonas = {json.dumps(zonas)};
        const focos = {json.dumps(focos)};

        const canvasRenderer = L.canvas({{ padding: 0.5 }});
        const map = L.map('map').setView([-16.6, -64.5], 6);

        L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
          maxZoom:19,
          attribution:'&copy; OpenStreetMap'
        }}).addTo(map);

        map.createPane('focosPane');
        map.getPane('focosPane').style.zIndex = 420;
        map.createPane('zonasPane');
        map.getPane('zonasPane').style.zIndex = 520;

        const layerZonas = L.layerGroup().addTo(map);
        const layerFocos = L.layerGroup().addTo(map);

        function focoColor(fuente) {{
          return (fuente || '').includes('VIIRS') ? '#dc2626' : '#f97316';
        }}

        function setMode(text) {{
          const el = document.getElementById('mode-label');
          if (el) el.innerText = text;
        }}

        zonas.forEach(z => {{
          const circle = L.circle([z.latitud, z.longitud], {{
            pane:'zonasPane',
            radius:z.radio_km*1000,
            color:'#2563eb',
            weight:4,
            fillColor:'#2563eb',
            fillOpacity:0.05
          }})
          .addTo(layerZonas)
          .bindPopup(`<b>Zona monitoreada</b><br>${{z.nombre_zona}}<br><b>Municipio:</b> ${{z.municipio || ''}}<br><b>Radio:</b> ${{z.radio_km}} km<br><b>Usuario:</b> ${{z.usuario_nombre || 'Sin usuario'}}`);

          L.circleMarker([z.latitud, z.longitud], {{
            pane:'zonasPane',
            radius:7,
            color:'#1d4ed8',
            fillColor:'#1d4ed8',
            fillOpacity:0.9,
            weight:2
          }})
          .addTo(layerZonas)
          .bindPopup(`<b>Centro de zona</b><br>${{z.nombre_zona}}`);
        }});

        focos.forEach(f => {{
          const color = focoColor(f.fuente);
          L.circleMarker([f.latitude, f.longitude], {{
            renderer: canvasRenderer,
            pane:'focosPane',
            radius:4,
            color:color,
            fillColor:color,
            fillOpacity:0.70,
            opacity:0.85,
            weight:1
          }})
          .addTo(layerFocos)
          .bindPopup(`<b>Foco de calor</b><br>${{f.fuente}}<br>${{f.acq_date}} ${{f.acq_time}}<br>Satélite: ${{f.satellite || ''}}<br>FRP: ${{f.frp || ''}}`);
        }});

        function addIfMissing(layer) {{
          if (!map.hasLayer(layer)) map.addLayer(layer);
        }}

        function removeIfPresent(layer) {{
          if (map.hasLayer(layer)) map.removeLayer(layer);
        }}

        function verZonas() {{
          addIfMissing(layerZonas);
          removeIfPresent(layerFocos);
          setMode('Zonas');
        }}

        function verFocos() {{
          removeIfPresent(layerZonas);
          addIfMissing(layerFocos);
          setMode('Focos');
        }}

        function verTodo() {{
          addIfMissing(layerZonas);
          addIfMissing(layerFocos);
          setMode('Todo');
        }}

        verTodo();
        </script>
        """
        return layout("Mapa", body)
    except Exception as exc:
        return error_page(exc)




@app.get("/usuarios", response_class=HTMLResponse)
def usuarios():
    try:
        conn = get_conn()
        rows_db = conn.execute("""
            SELECT u.*, COUNT(z.id) AS total_zonas
            FROM usuarios u LEFT JOIN zonas z ON z.usuario_id=u.id
            GROUP BY u.id ORDER BY u.activo DESC, u.nombre
        """).fetchall()
        conn.close()

        cards = ""
        for u in rows_db:
            estado = "Activo" if u["activo"] else "Inactivo"
            cards += f"""
            <div class="user-card">
              <h3>{esc(u['nombre'])}</h3>
              <p><strong>Tipo:</strong> {esc(u['tipo_usuario'] or '')}</p>
              <p><strong>Organización:</strong> {esc(u['organizacion'] or '')}</p>
              <p><strong>Correo:</strong> {esc(u['email'] or '')}</p>
              <p><strong>Teléfono:</strong> {esc(u['telefono'] or '')}</p>
              <p><strong>Zonas asociadas:</strong> {esc(u['total_zonas'])}</p>
              <p><strong>Estado:</strong> {esc(estado)}</p>
              <p><a class="button light" href="/usuarios/{u['id']}/editar">Editar usuario</a></p>
            </div>
            """
        if not cards:
            cards = "<p>No hay usuarios registrados.</p>"

        body = f"""
        <div class="card">
          <h2>Usuarios y responsables</h2>
          <p>Registra personas, responsables de predios, comunidades o instituciones.</p>
          <p><a class="button" href="/usuarios/nuevo">Nuevo usuario</a></p>
        </div>
        <div class="user-grid">{cards}</div>
        """
        return layout("Usuarios", body)
    except Exception as exc:
        return error_page(exc)


@app.get("/usuarios/nuevo", response_class=HTMLResponse)
def usuario_nuevo_form():
    body = """
    <div class="card">
      <h2>Nuevo usuario</h2>
      <form method="post" action="/usuarios/nuevo">
        <div class="form-grid">
          <div><label>Nombre</label><input name="nombre" required placeholder="Ej. Juan Pérez"></div>
          <div><label>Teléfono / WhatsApp</label><input name="telefono" placeholder="+591..."></div>
          <div><label>Correo</label><input name="email" type="email" placeholder="correo@ejemplo.com"></div>
          <div><label>Organización</label><input name="organizacion" placeholder="Predio, comunidad, municipio..."></div>
          <div><label>Tipo de usuario</label><select name="tipo_usuario"><option>Propietario</option><option>Comunidad</option><option>Municipal</option><option>Institucional</option><option>Operador</option><option>Piloto</option></select></div>
        </div>
        <p><button type="submit">Guardar usuario</button></p>
      </form>
    </div>
    """
    return layout("Nuevo usuario", body)


@app.post("/usuarios/nuevo")
def usuario_nuevo(nombre: str = Form(...), telefono: str = Form(""), email: str = Form(""), organizacion: str = Form(""), tipo_usuario: str = Form("Propietario")):
    conn = get_conn()
    conn.execute("""
        INSERT INTO usuarios (nombre, email, telefono, organizacion, tipo_usuario, activo, creado_utc)
        VALUES (?, ?, ?, ?, ?, 1, ?)
    """, (nombre, email, telefono, organizacion, tipo_usuario, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()
    return RedirectResponse("/usuarios", status_code=303)


@app.get("/usuarios/{usuario_id}/editar", response_class=HTMLResponse)
def usuario_editar_form(usuario_id: int):
    try:
        conn = get_conn()
        u = conn.execute("SELECT * FROM usuarios WHERE id=?", (usuario_id,)).fetchone()
        zonas_user = conn.execute("SELECT * FROM zonas WHERE usuario_id=? ORDER BY nombre_zona", (usuario_id,)).fetchall()
        conn.close()
        if not u:
            return layout("Usuario no encontrado", "<div class='card'><h2>Usuario no encontrado</h2></div>")

        zonas_rows = ""
        for z in zonas_user:
            zonas_rows += f"<tr><td>{esc(z['nombre_zona'])}</td><td>{esc(z['municipio'])}</td><td>{esc(z['radio_km'])} km</td><td><a href='/zonas/{z['id']}/editar'>Editar zona</a></td></tr>"
        if not zonas_rows:
            zonas_rows = "<tr><td colspan='4'>Este usuario aún no tiene zonas asociadas.</td></tr>"

        body = f"""
        <div class="card">
          <h2>Editar usuario</h2>
          <form method="post" action="/usuarios/{esc(usuario_id)}/editar">
            <div class="form-grid">
              <div><label>Nombre</label><input name="nombre" value="{esc(u['nombre'])}" required></div>
              <div><label>Teléfono / WhatsApp</label><input name="telefono" value="{esc(u['telefono'] or '')}"></div>
              <div><label>Correo</label><input name="email" type="email" value="{esc(u['email'] or '')}"></div>
              <div><label>Organización</label><input name="organizacion" value="{esc(u['organizacion'] or '')}"></div>
              <div><label>Tipo</label><input name="tipo_usuario" value="{esc(u['tipo_usuario'] or '')}"></div>
              <div><label>Estado</label><select name="activo"><option value="1" {"selected" if u["activo"] else ""}>Activo</option><option value="0" {"" if u["activo"] else "selected"}>Inactivo</option></select></div>
            </div>
            <p><button type="submit">Guardar usuario</button> <a class="button light" href="/usuarios">Volver</a></p>
          </form>
        </div>
        <div class="card">
          <h2>Zonas asociadas</h2>
          <table><thead><tr><th>Zona</th><th>Municipio</th><th>Radio</th><th>Acción</th></tr></thead><tbody>{zonas_rows}</tbody></table>
          <p><a class="button" href="/zonas/nueva">Crear nueva zona</a></p>
        </div>
        """
        return layout("Editar usuario", body)
    except Exception as exc:
        return error_page(exc)


@app.post("/usuarios/{usuario_id}/editar")
def usuario_editar(usuario_id: int, nombre: str = Form(...), telefono: str = Form(""), email: str = Form(""), organizacion: str = Form(""), tipo_usuario: str = Form(""), activo: int = Form(1)):
    conn = get_conn()
    conn.execute("""
        UPDATE usuarios SET nombre=?, telefono=?, email=?, organizacion=?, tipo_usuario=?, activo=? WHERE id=?
    """, (nombre, telefono, email, organizacion, tipo_usuario, activo, usuario_id))
    conn.commit()
    conn.close()
    return RedirectResponse("/usuarios", status_code=303)


@app.get("/zonas", response_class=HTMLResponse)
def zonas():
    try:
        conn = get_conn()
        rows_db = conn.execute("""
            SELECT z.*, u.nombre AS usuario_nombre, u.telefono AS usuario_telefono, u.email AS usuario_email
            FROM zonas z LEFT JOIN usuarios u ON u.id=z.usuario_id
            ORDER BY z.id
        """).fetchall()
        conn.close()
        rows = ""
        for z in rows_db:
            estado = "Activa" if z["activa"] else "Inactiva"
            usuario = z["usuario_nombre"] or "Sin usuario"
            rows += f"""
            <tr>
              <td>{esc(z['nombre_zona'])}</td><td>{esc(usuario)}</td><td>{esc(z['tipo_zona'])}</td><td>{esc(z['municipio'])}</td>
              <td>{esc(z['latitud'])}, {esc(z['longitud'])}</td><td><strong>{esc(z['radio_km'])} km</strong></td><td>{esc(estado)}</td>
              <td><a class="button light" href="/zonas/{z['id']}/editar">Editar</a></td>
            </tr>"""
        body = f"""
        <div class="card">
          <h2>Zonas registradas</h2>
          <p>Cada zona puede estar asociada a un usuario o responsable.</p>
          <p><a class="button" href="/zonas/nueva">Nueva zona</a> <a class="button light" href="/usuarios/nuevo">Nuevo usuario</a>
          <form method="post" action="/recalcular-alertas" style="display:inline-block;"><button class="secondary" type="submit">Recalcular alertas</button></form>
          <form method="post" action="/zonas/radio-recomendado" style="display:inline-block;"><button class="secondary" type="submit">Aplicar radio recomendado</button></form></p>
          <table><thead><tr><th>Zona</th><th>Usuario</th><th>Tipo</th><th>Municipio</th><th>Coordenadas</th><th>Radio</th><th>Estado</th><th>Acción</th></tr></thead><tbody>{rows}</tbody></table>
        </div>
        <div class="geo-help">En celular, al crear o editar una zona puedes tocar “Usar mi ubicación actual”.</div>
        """
        return layout("Zonas", body)
    except Exception as exc:
        return error_page(exc)


def user_options_html(selected_id=None):
    conn = get_conn()
    usuarios = conn.execute("SELECT * FROM usuarios WHERE activo=1 ORDER BY nombre").fetchall()
    conn.close()
    options = '<option value="">Sin usuario asignado</option>'
    for u in usuarios:
        sel = "selected" if selected_id == u["id"] else ""
        options += f'<option value="{u["id"]}" {sel}>{esc(u["nombre"])} — {esc(u["telefono"] or u["email"] or "")}</option>'
    return options


@app.get("/zonas/nueva", response_class=HTMLResponse)
def zona_form():
    options = user_options_html()
    body = f"""
    <div class="card">
      <h2>Nueva zona</h2>
      <div class="geo-help">Si estás en el lugar, presiona <strong>Usar mi ubicación actual</strong> para llenar latitud y longitud.</div>
      <form method="post" action="/zonas/nueva">
        <div class="form-grid">
          <div><label>Usuario responsable</label><select name="usuario_id">{options}</select></div>
          <div><label>Nombre de la zona</label><input name="nombre_zona" required placeholder="Ej. Predio San José"></div>
          <div><label>Correo de contacto</label><input name="contacto_email" type="email" placeholder="correo@ejemplo.com"></div>
          <div><label>Tipo</label><select name="tipo_zona"><option>Predio</option><option>Comunidad</option><option>Municipio</option><option>Área protegida</option><option>Proyecto</option><option>Ubicación actual</option></select></div>
          <div><label>Departamento</label><input name="departamento" value="Santa Cruz"></div>
          <div><label>Municipio</label><input name="municipio" placeholder="Ej. Roboré"></div>
          <div><label>Latitud</label><input name="latitud" type="number" step="any" required placeholder="-17.0000000"></div>
          <div><label>Longitud</label><input name="longitud" type="number" step="any" required placeholder="-60.0000000"></div>
          <div><label>Radio km</label><select name="radio_km">{radio_options_html(DEFAULT_ZONE_RADIUS_KM)}</select></div>
        </div>
        <p><button id="geo-btn" type="button" onclick="usarUbicacionActual()">Usar mi ubicación actual</button> <button type="submit">Guardar zona</button></p>
      </form>
    </div>
    """
    return layout("Nueva zona", body)


@app.post("/zonas/nueva")
def zona_nueva(nombre_zona: str = Form(...), contacto_email: str = Form(""), tipo_zona: str = Form("Predio"), departamento: str = Form("Santa Cruz"), municipio: str = Form(""), latitud: float = Form(...), longitud: float = Form(...), radio_km: float = Form(DEFAULT_ZONE_RADIUS_KM), usuario_id: str = Form("")):
    uid = int(usuario_id) if str(usuario_id).strip() else None
    if not contacto_email and uid:
        conn_tmp = get_conn()
        u = conn_tmp.execute("SELECT email FROM usuarios WHERE id=?", (uid,)).fetchone()
        conn_tmp.close()
        contacto_email = u["email"] if u and u["email"] else "sin-correo@camposeguro.local"
    if not contacto_email:
        contacto_email = "sin-correo@camposeguro.local"

    conn = get_conn()
    conn.execute("""
        INSERT INTO zonas (usuario_id, nombre_zona, contacto_email, tipo_zona, departamento, municipio, latitud, longitud, radio_km, activa, creada_utc)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
    """, (uid, nombre_zona, contacto_email, tipo_zona, departamento, municipio, latitud, longitud, radio_km, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()
    return RedirectResponse("/zonas", status_code=303)


@app.get("/zonas/{zona_id}/editar", response_class=HTMLResponse)
def zona_editar_form(zona_id: int):
    try:
        conn = get_conn()
        z = conn.execute("SELECT * FROM zonas WHERE id=?", (zona_id,)).fetchone()
        conn.close()
        if not z:
            return layout("Zona no encontrada", "<div class='card'><h2>Zona no encontrada</h2></div>")

        def selected(value):
            return "selected" if float(z["radio_km"]) == float(value) else ""

        options = user_options_html(z["usuario_id"])
        body = f"""
        <div class="card">
          <h2>Editar zona</h2>
          <div class="geo-help">Puedes reemplazar las coordenadas con la ubicación actual del teléfono.</div>
          <form method="post" action="/zonas/{esc(zona_id)}/editar">
            <div class="form-grid">
              <div><label>Usuario responsable</label><select name="usuario_id">{options}</select></div>
              <div><label>Nombre</label><input name="nombre_zona" value="{esc(z['nombre_zona'])}" required></div>
              <div><label>Correo</label><input name="contacto_email" type="email" value="{esc(z['contacto_email'] or '')}"></div>
              <div><label>Tipo</label><input name="tipo_zona" value="{esc(z['tipo_zona'] or '')}"></div>
              <div><label>Municipio</label><input name="municipio" value="{esc(z['municipio'] or '')}"></div>
              <div><label>Latitud</label><input name="latitud" type="number" step="any" value="{esc(z['latitud'])}" required></div>
              <div><label>Longitud</label><input name="longitud" type="number" step="any" value="{esc(z['longitud'])}" required></div>
              <div><label>Radio</label><select name="radio_km">{radio_options_html(z["radio_km"])}</select></div>
              <div><label>Estado</label><select name="activa"><option value="1" {"selected" if z["activa"] else ""}>Activa</option><option value="0" {"" if z["activa"] else "selected"}>Inactiva</option></select></div>
            </div>
            <p><button id="geo-btn" type="button" onclick="usarUbicacionActual()">Usar mi ubicación actual</button> <button type="submit">Guardar y recalcular</button> <a class="button light" href="/zonas">Volver</a></p>
          </form>
        </div>
        """
        return layout("Editar zona", body)
    except Exception as exc:
        return error_page(exc)


@app.post("/zonas/{zona_id}/editar")
def zona_editar(zona_id: int, nombre_zona: str = Form(...), contacto_email: str = Form(""), tipo_zona: str = Form("Predio"), municipio: str = Form(""), latitud: float = Form(...), longitud: float = Form(...), radio_km: float = Form(DEFAULT_ZONE_RADIUS_KM), activa: int = Form(1), usuario_id: str = Form("")):
    uid = int(usuario_id) if str(usuario_id).strip() else None
    if not contacto_email and uid:
        conn_tmp = get_conn()
        u = conn_tmp.execute("SELECT email FROM usuarios WHERE id=?", (uid,)).fetchone()
        conn_tmp.close()
        contacto_email = u["email"] if u and u["email"] else "sin-correo@camposeguro.local"
    if not contacto_email:
        contacto_email = "sin-correo@camposeguro.local"

    conn = get_conn()
    conn.execute("""
        UPDATE zonas SET usuario_id=?, nombre_zona=?, contacto_email=?, tipo_zona=?, municipio=?, latitud=?, longitud=?, radio_km=?, activa=? WHERE id=?
    """, (uid, nombre_zona, contacto_email, tipo_zona, municipio, latitud, longitud, radio_km, activa, zona_id))
    conn.commit()
    conn.close()
    recalcular_alertas_existentes()
    return RedirectResponse("/zonas", status_code=303)



@app.post("/zonas/radio-recomendado")
def zonas_radio_recomendado():
    conn = get_conn()
    conn.execute("UPDATE zonas SET radio_km=? WHERE activa=1", (DEFAULT_ZONE_RADIUS_KM,))
    conn.commit()
    conn.close()
    recalcular_alertas_existentes()
    return RedirectResponse("/zonas", status_code=303)


@app.post("/recalcular-alertas")
def recalcular_alertas():
    recalcular_alertas_existentes()
    return RedirectResponse("/alertas", status_code=303)


@app.get("/alertas", response_class=HTMLResponse)
def alertas():
    try:
        conn = get_conn()
        rows_db = conn.execute("""
            SELECT a.*, z.nombre_zona, z.municipio, u.nombre AS usuario_nombre, u.telefono AS usuario_telefono,
                   f.latitude, f.longitude, f.acq_date, f.acq_time, f.fuente
            FROM alertas a
            JOIN zonas z ON z.id=a.zona_id
            LEFT JOIN usuarios u ON u.id=z.usuario_id
            JOIN focos f ON f.id=a.foco_id
            ORDER BY CASE WHEN a.nivel='CRITICO' THEN 1 WHEN a.nivel='ATENCION' THEN 2 ELSE 3 END, a.distancia_km ASC
            LIMIT 1000
        """).fetchall()
        conn.close()
        if not rows_db:
            return layout("Alertas", "<div class='card'><h2>Alertas</h2><p>No hay alertas registradas.</p></div>")

        cards = ""
        table_rows = ""
        for idx, a in enumerate(rows_db, start=1):
            rec = recomendacion_por_nivel(a["nivel"])
            msg = mensaje_alerta(a)
            cards += f"""
            <div class="alert-card {esc(a['nivel'])}">
              <div class="alert-title"><h3>{esc(a['nombre_zona'])}</h3><span class="badge {esc(a['nivel'])}">{esc(a['nivel'])}</span></div>
              <div class="alert-meta">
                <div><strong>Usuario</strong><br>{esc(a['usuario_nombre'] or 'Sin usuario')}</div>
                <div><strong>Municipio</strong><br>{esc(a['municipio'])}</div>
                <div><strong>Distancia</strong><br>{esc(a['distancia_km'])} km</div>
                <div><strong>Fuente</strong><br>{esc(a['fuente'])}</div>
                <div><strong>Fecha</strong><br>{esc(a['acq_date'])} {esc(a['acq_time'])}</div>
                <div><strong>Teléfono</strong><br>{esc(a['usuario_telefono'] or '')}</div>
              </div>
              <p><strong>Recomendación:</strong> {esc(rec)}</p>
              <div class="message-box" id="msg-{idx}">{esc(msg)}</div>
              <button class="copy-button" type="button" onclick="copiarTexto('msg-{idx}')">Copiar mensaje</button>
              <a class="button light" target="_blank" href="https://www.google.com/maps?q={esc(a['latitude'])},{esc(a['longitude'])}">Abrir foco en mapa</a>
            </div>
            """
            table_rows += f"<tr><td><span class='badge {esc(a['nivel'])}'>{esc(a['nivel'])}</span></td><td>{esc(a['nombre_zona'])}</td><td>{esc(a['usuario_nombre'] or '')}</td><td>{esc(a['distancia_km'])} km</td><td>{esc(a['fuente'])}</td><td>{esc(a['acq_date'])} {esc(a['acq_time'])}</td></tr>"

        body = f"""
        <div class="card"><h2>Panel de alertas</h2><p>Alertas ordenadas por prioridad y distancia.</p></div>
        <div class="alert-grid">{cards}</div>
        <div class="card"><h2>Tabla técnica</h2><table><thead><tr><th>Nivel</th><th>Zona</th><th>Usuario</th><th>Distancia</th><th>Fuente</th><th>Fecha</th></tr></thead><tbody>{table_rows}</tbody></table></div>
        """
        return layout("Alertas", body)
    except Exception as exc:
        return error_page(exc)


@app.get("/focos", response_class=HTMLResponse)
def focos():
    try:
        conn = get_conn()
        rows_db = conn.execute("SELECT * FROM focos ORDER BY acq_date DESC, acq_time DESC LIMIT 1000").fetchall()
        conn.close()
        rows = ""
        for f in rows_db:
            rows += f"<tr><td>{esc(f['fuente'])}</td><td>{esc(f['latitude'])}</td><td>{esc(f['longitude'])}</td><td>{esc(f['acq_date'])}</td><td>{esc(f['acq_time'])}</td><td>{esc(f['satellite'])}</td><td>{esc(f['confidence'])}</td><td>{esc(f['frp'])}</td></tr>"
        content = "<p>No hay focos guardados.</p>" if not rows else f"<table><thead><tr><th>Fuente</th><th>Lat</th><th>Lon</th><th>Fecha</th><th>Hora</th><th>Satélite</th><th>Confianza</th><th>FRP</th></tr></thead><tbody>{rows}</tbody></table>"
        return layout("Focos", f"<div class='card'><h2>Focos FIRMS</h2>{content}</div>")
    except Exception as exc:
        return error_page(exc)


def datos_resumen():
    conn = get_conn()
    general = conn.execute("""
        SELECT COUNT(*) AS total_alertas,
               SUM(CASE WHEN nivel='CRITICO' THEN 1 ELSE 0 END) AS criticas,
               SUM(CASE WHEN nivel='ATENCION' THEN 1 ELSE 0 END) AS atencion,
               SUM(CASE WHEN nivel='INFORMATIVO' THEN 1 ELSE 0 END) AS informativas,
               MIN(distancia_km) AS distancia_minima
        FROM alertas
    """).fetchone()
    total_focos = conn.execute("SELECT COUNT(*) FROM focos").fetchone()[0]
    total_zonas = conn.execute("SELECT COUNT(*) FROM zonas WHERE activa=1").fetchone()[0]
    por_zona = conn.execute("""
        SELECT z.nombre_zona, z.municipio, u.nombre AS usuario_nombre,
               COUNT(*) AS total_alertas, MIN(a.distancia_km) AS distancia_minima,
               MAX(CASE WHEN a.nivel='CRITICO' THEN 3 WHEN a.nivel='ATENCION' THEN 2 ELSE 1 END) AS nivel_max_num,
               MAX(f.acq_date || ' ' || f.acq_time) AS ultima_deteccion
        FROM alertas a JOIN zonas z ON z.id=a.zona_id LEFT JOIN usuarios u ON u.id=z.usuario_id JOIN focos f ON f.id=a.foco_id
        GROUP BY z.id ORDER BY total_alertas DESC, distancia_minima ASC
    """).fetchall()
    focos_fuente = conn.execute("SELECT fuente, COUNT(*) AS total, MAX(acq_date || ' ' || acq_time) AS ultima_deteccion FROM focos GROUP BY fuente ORDER BY total DESC").fetchall()
    conn.close()
    return general, total_focos, total_zonas, por_zona, focos_fuente


@app.get("/resumen", response_class=HTMLResponse)
def resumen():
    try:
        general, total_focos, total_zonas, por_zona, focos_fuente = datos_resumen()
        nivel_map = {3: "CRITICO", 2: "ATENCION", 1: "INFORMATIVO"}
        cards = ""
        for z in por_zona:
            nivel = nivel_map.get(z["nivel_max_num"], "INFORMATIVO")
            cards += f"<div class='zone-card'><h3>{esc(z['nombre_zona'])}</h3><p><strong>Usuario:</strong> {esc(z['usuario_nombre'] or '')}</p><p><strong>Municipio:</strong> {esc(z['municipio'])}</p><p><strong>Alertas:</strong> {esc(z['total_alertas'])}</p><p><strong>Nivel máximo:</strong> <span class='badge {esc(nivel)}'>{esc(nivel)}</span></p><p><strong>Distancia mínima:</strong> {esc(round(z['distancia_minima'],2))} km</p><p><strong>Última detección:</strong> {esc(z['ultima_deteccion'])}</p></div>"
        if not cards:
            cards = "<p>No hay alertas para resumir.</p>"
        fuente_rows = "".join([f"<tr><td>{esc(f['fuente'])}</td><td>{esc(f['total'])}</td><td>{esc(f['ultima_deteccion'])}</td></tr>" for f in focos_fuente])
        body = f"""
        <div class="card"><h2>Resumen ejecutivo</h2>
          <div class="grid">
            <div class="card"><div class="metric-label">Zonas activas</div><div class="metric">{esc(total_zonas)}</div></div>
            <div class="card"><div class="metric-label">Focos FIRMS</div><div class="metric">{esc(total_focos)}</div></div>
            <div class="card"><div class="metric-label">Alertas</div><div class="metric">{esc(general['total_alertas'] or 0)}</div></div>
            <div class="card"><div class="metric-label">Críticas</div><div class="metric">{esc(general['criticas'] or 0)}</div></div>
          </div>
          <p><a class="button" href="/exportar/alertas.csv">Exportar alertas CSV</a> <a class="button light" href="/exportar/focos.csv">Exportar focos CSV</a></p>
        </div>
        <div class="card"><h2>Resumen por zona</h2><div class="zone-summary">{cards}</div></div>
        <div class="card"><h2>Focos por fuente</h2><table><thead><tr><th>Fuente</th><th>Total</th><th>Última detección</th></tr></thead><tbody>{fuente_rows}</tbody></table></div>
        """
        return layout("Resumen", body)
    except Exception as exc:
        return error_page(exc)


def csv_response(filename, headers, rows):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([row.get(h, "") for h in headers])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.get("/exportar/alertas.csv")
def exportar_alertas():
    conn = get_conn()
    rows = rows_to_dicts(conn.execute("""
        SELECT a.nivel, z.nombre_zona, z.municipio, u.nombre AS usuario_nombre, u.telefono AS usuario_telefono,
               a.distancia_km, f.fuente, f.latitude, f.longitude, f.acq_date, f.acq_time, f.satellite, f.confidence, f.frp
        FROM alertas a JOIN zonas z ON z.id=a.zona_id LEFT JOIN usuarios u ON u.id=z.usuario_id JOIN focos f ON f.id=a.foco_id
        ORDER BY a.creada_utc DESC
    """).fetchall())
    conn.close()
    headers = ["nivel", "nombre_zona", "municipio", "usuario_nombre", "usuario_telefono", "distancia_km", "fuente", "latitude", "longitude", "acq_date", "acq_time", "satellite", "confidence", "frp"]
    return csv_response("camposeguro_alertas.csv", headers, rows)


@app.get("/exportar/focos.csv")
def exportar_focos():
    conn = get_conn()
    rows = rows_to_dicts(conn.execute("SELECT fuente, latitude, longitude, acq_date, acq_time, satellite, instrument, confidence, frp, bright_ti4, daynight FROM focos ORDER BY acq_date DESC, acq_time DESC").fetchall())
    conn.close()
    headers = ["fuente", "latitude", "longitude", "acq_date", "acq_time", "satellite", "instrument", "confidence", "frp", "bright_ti4", "daynight"]
    return csv_response("camposeguro_focos.csv", headers, rows)


@app.get("/reporte", response_class=HTMLResponse)
def reporte():
    try:
        general, total_focos, total_zonas, por_zona, focos_fuente = datos_resumen()
        fecha_reporte = datetime.now(timezone.utc).isoformat(timespec="seconds")
        nivel_map = {3: "CRITICO", 2: "ATENCION", 1: "INFORMATIVO"}
        zona_rows = ""
        for z in por_zona:
            nivel = nivel_map.get(z["nivel_max_num"], "INFORMATIVO")
            zona_rows += f"<tr><td>{esc(z['nombre_zona'])}</td><td>{esc(z['usuario_nombre'] or '')}</td><td>{esc(z['municipio'])}</td><td>{esc(z['total_alertas'])}</td><td><span class='badge {esc(nivel)}'>{esc(nivel)}</span></td><td>{esc(round(z['distancia_minima'],2))} km</td><td>{esc(z['ultima_deteccion'])}</td></tr>"
        if not zona_rows:
            zona_rows = "<tr><td colspan='7'>Sin alertas.</td></tr>"

        body = f"""
        <div class="card">
          <div class="report-header"><div><h2>Reporte operativo CampoSeguro</h2><p>Monitoreo informativo de focos de calor cercanos a zonas registradas.</p></div><div class="report-meta"><strong>Fecha UTC</strong><br>{esc(fecha_reporte)}<br><br><strong>Fuente</strong><br>NASA FIRMS Area API</div></div>
          <div class="print-actions"><button onclick="window.print()">Imprimir / Guardar PDF</button><a class="button light" href="/exportar/alertas.csv">Exportar alertas CSV</a><a class="button light" href="/exportar/mensajes.txt">Descargar mensajes</a></div>
          <div class="report-kpis"><div class="report-kpi"><span>Zonas activas</span><strong>{esc(total_zonas)}</strong></div><div class="report-kpi"><span>Focos FIRMS</span><strong>{esc(total_focos)}</strong></div><div class="report-kpi"><span>Alertas</span><strong>{esc(general['total_alertas'] or 0)}</strong></div><div class="report-kpi"><span>Críticas</span><strong>{esc(general['criticas'] or 0)}</strong></div></div>
          <h3>Resumen por zona</h3>
          <table><thead><tr><th>Zona</th><th>Usuario</th><th>Municipio</th><th>Alertas</th><th>Nivel máximo</th><th>Distancia mínima</th><th>Última detección</th></tr></thead><tbody>{zona_rows}</tbody></table>
          <div class="notice">CampoSeguro es una herramienta informativa. No reemplaza verificación en campo ni sistemas oficiales de emergencia.</div>
        </div>
        """
        return layout("Reporte", body)
    except Exception as exc:
        return error_page(exc)


@app.get("/exportar/mensajes.txt")
def exportar_mensajes():
    conn = get_conn()
    rows = conn.execute("""
        SELECT a.*, z.nombre_zona, z.municipio, f.acq_date, f.acq_time, f.fuente
        FROM alertas a JOIN zonas z ON z.id=a.zona_id JOIN focos f ON f.id=a.foco_id
        ORDER BY CASE WHEN a.nivel='CRITICO' THEN 1 WHEN a.nivel='ATENCION' THEN 2 ELSE 3 END, a.distancia_km ASC
    """).fetchall()
    conn.close()
    parts = []
    for idx, a in enumerate(rows, start=1):
        parts.append(f"ALERTA {idx} - {a['nombre_zona']}\n{mensaje_alerta(a)}\n")
    text = "\n".join(parts) if parts else "No hay mensajes de alerta generados."
    return StreamingResponse(iter([text]), media_type="text/plain", headers={"Content-Disposition": "attachment; filename=camposeguro_mensajes_alerta.txt"})




@app.get("/correos", response_class=HTMLResponse)
def correos():
    try:
        stats_mail = estadisticas_correos()
        rows_db = listar_correos()
        smtp_estado = "Envío real activo" if smtp_config_ok() else "Modo seguro/local: genera archivos en output/outbox_email"
        rows = ""
        for c in rows_db:
            rows += f"""
            <tr>
              <td>{esc(c['estado'])}</td><td>{esc(c['destinatario'])}</td><td>{esc(c['nombre_zona'])}</td><td>{esc(c['nivel'])}</td>
              <td>{esc(c['creado_utc'])}</td><td>{esc(c['enviado_utc'] or '')}</td><td>{esc(c['error'] or '')}</td>
            </tr>"""
        if not rows:
            rows = "<tr><td colspan='7'>No hay correos preparados todavía.</td></tr>"
        body = f"""
        <div class="card">
          <h2>Correos de alerta</h2>
          <p><strong>Estado:</strong> {esc(smtp_estado)}</p>
          <div class="grid">
            <div class="card"><div class="metric-label">Pendientes</div><div class="metric">{esc(stats_mail['pendientes'])}</div></div>
            <div class="card"><div class="metric-label">Enviados</div><div class="metric">{esc(stats_mail['enviados'])}</div></div>
            <div class="card"><div class="metric-label">Outbox local</div><div class="metric">{esc(stats_mail['outbox'])}</div></div>
            <div class="card"><div class="metric-label">Errores</div><div class="metric">{esc(stats_mail['errores'])}</div></div>
          </div>
          <form method="post" action="/correos/preparar" style="display:inline-block;"><button type="submit">Preparar correos</button></form>
          <form method="post" action="/correos/enviar" style="display:inline-block;"><button type="submit">Procesar correos pendientes</button></form>
        </div>
        <div class="notice">
          Si EMAIL_ENABLED=false, CampoSeguro no envía correos reales: genera archivos TXT en <strong>output/outbox_email</strong>.
          Para Resend usar: smtp.resend.com, puerto 465, SSL activo, usuario resend.
        </div>
        <div class="card">
          <h2>Prueba de correo SMTP</h2>
          <p><strong>EMAIL_ENABLED:</strong> {esc(EMAIL_ENABLED)}</p>
          <p><strong>SMTP:</strong> {esc(SMTP_HOST or "No configurado")}:{esc(SMTP_PORT)} |
             SSL: {esc(SMTP_USE_SSL)} | STARTTLS: {esc(SMTP_USE_TLS)}</p>
          <p><strong>Usuario SMTP:</strong> {esc(SMTP_USER or "No configurado")}</p>
          <p><strong>Remitente:</strong> {esc(SMTP_FROM or "No configurado")}</p>
          <p><strong>Reply-To:</strong> {esc(EMAIL_REPLY_TO or "No configurado")}</p>
          <form method="post" action="/correos/prueba" style="display:flex; gap:8px; flex-wrap:wrap; align-items:end;">
            <div style="min-width:280px;">
              <label>Enviar prueba a</label>
              <input type="email" name="destinatario" placeholder="tu_correo@gmail.com" required>
            </div>
            <button type="submit">Enviar prueba</button>
          </form>
        </div>
        <div class="card"><h2>Historial de correos</h2><table><thead><tr><th>Estado</th><th>Destinatario</th><th>Zona</th><th>Nivel</th><th>Creado</th><th>Procesado</th><th>Mensaje/Error</th></tr></thead><tbody>{rows}</tbody></table></div>
        """
        return layout("Correos", body)
    except Exception as exc:
        return error_page(exc)


@app.post("/correos/preparar", response_class=HTMLResponse)
def correos_preparar():
    try:
        creados = preparar_correos_pendientes()
        return layout("Correos preparados", f"<div class='card'><h2>Correos preparados</h2><p><strong>Nuevos correos:</strong> {esc(creados)}</p><p><a class='button' href='/correos'>Volver</a></p></div>")
    except Exception as exc:
        return error_page(exc)


@app.post("/correos/enviar", response_class=HTMLResponse)
def correos_enviar():
    try:
        r = procesar_correos_pendientes()
        body = f"""
        <div class="card"><h2>Correos procesados</h2>
          <p><strong>Procesados:</strong> {esc(r['procesados'])}</p>
          <p><strong>Enviados reales:</strong> {esc(r['enviados'])}</p>
          <p><strong>Outbox local:</strong> {esc(r['outbox'])}</p>
          <p><strong>Errores:</strong> {esc(r['errores'])}</p>
          <p><strong>SMTP activo:</strong> {esc(r['smtp_activo'])}</p>
          <p><a class="button" href="/correos">Volver</a></p>
        </div>"""
        return layout("Correos procesados", body)
    except Exception as exc:
        return error_page(exc)






@app.post("/correos/prueba", response_class=HTMLResponse)
def correos_prueba(destinatario: str = Form(...)):
    try:
        if not smtp_config_ok():
            body = f"""
            <div class="card">
              <h2>No se pudo enviar la prueba</h2>
              <p>SMTP todavía no está activo. Revisa estas variables en Render:</p>
              <pre>EMAIL_ENABLED=true
SMTP_HOST=smtp.resend.com
SMTP_PORT=465
SMTP_USE_SSL=true
SMTP_USE_TLS=false
SMTP_USER=resend
SMTP_PASSWORD=tu_api_key_de_resend
SMTP_FROM=CampoSeguro &lt;alertas@camposeguro.app&gt;</pre>
              <p><a class="button" href="/correos">Volver</a></p>
            </div>
            """
            return layout("Prueba de correo", body)

        enviar_correo_prueba(destinatario.strip())
        body = f"""
        <div class="card">
          <h2>Correo de prueba enviado</h2>
          <p>Se envió un mensaje de prueba a:</p>
          <p><strong>{esc(destinatario)}</strong></p>
          <p>Revisa también spam/promociones si no aparece en la bandeja principal.</p>
          <p><a class="button" href="/correos">Volver a correos</a></p>
        </div>
        """
        return layout("Prueba de correo", body)
    except Exception as exc:
        body = f"""
        <div class="card">
          <h2>Error enviando prueba</h2>
          <p>El servidor SMTP respondió con error:</p>
          <pre>{esc(str(exc))}</pre>
          <p><a class="button" href="/correos">Volver</a></p>
        </div>
        """
        return layout("Error correo", body)


@app.get("/prueba-firms", response_class=HTMLResponse)
def prueba_firms(bbox: str = "", days: int = 1, preset: str = ""):
    try:
        if preset in AREA_PRESETS:
            bbox_actual = AREA_PRESETS[preset]
            preset_actual = preset
        else:
            bbox_actual = bbox or FIRMS_AREA_BBOX
            preset_actual = "Personalizada"

        dias = int(days or FIRMS_DAY_RANGE)
        tests = []
        for source in FIRMS_SOURCES:
            tests.append(test_source(source, bbox=bbox_actual, days=dias))

        rows = ""
        total = 0
        details = ""
        for t in tests:
            total += int(t["parsed_count"] or 0)
            estado = "OK" if t["ok"] else "ERROR"
            rows += f"""
            <tr>
              <td>{esc(t['source'])}</td>
              <td>{esc(estado)}</td>
              <td>{esc(t['status_code'])}</td>
              <td>{esc(t['parsed_count'])}</td>
              <td>{esc(t['url'])}</td>
              <td>{esc(t['error'] or t['parse_message'])}</td>
            </tr>
            """
            details += f"""
            <div class="card">
              <h3>{esc(t['source'])}</h3>
              <p><strong>URL:</strong> {esc(t['url'])}</p>
              <p><strong>Status:</strong> {esc(t['status_code'])} | <strong>Filas leídas:</strong> {esc(t['parsed_count'])}</p>
              <pre>{esc(t['first_lines'] or t['error'] or 'Sin contenido')}</pre>
            </div>
            """

        body = f"""
        <div class="card">
          <h2>Prueba técnica FIRMS</h2>
          <p>La API usada es regional: <strong>{esc(API_REGION_LABEL)}</strong>. CampoSeguro consulta por BBOX operativo, no toda Sudamérica.</p>
          <p><strong>Llave actual:</strong> {esc(masked_key())}</p>
          <p><strong>Área de prueba:</strong> {esc(preset_actual)}</p>
          <p><strong>BBOX usado:</strong> {esc(bbox_actual)}</p>
          <p><strong>Días usados:</strong> {esc(dias)}</p>
          <p><strong>Total de filas leídas:</strong> {esc(total)}</p>

          <form method="get" action="/prueba-firms">
            <div class="form-grid">
              <div>
                <label>BBOX de prueba</label>
                <input name="bbox" value="{esc(bbox_actual)}">
              </div>
              <div>
                <label>Días</label>
                <select name="days">
                  <option value="1" {"selected" if dias == 1 else ""}>1 día</option>
                  <option value="3" {"selected" if dias == 3 else ""}>3 días</option>
                  <option value="5" {"selected" if dias == 5 else ""}>5 días</option>
                  <option value="10" {"selected" if dias == 10 else ""}>10 días</option>
                </select>
              </div>
            </div>
            <p><button type="submit">Probar BBOX personalizada</button></p>
          </form>

          <p>
            <a class="button light" href="/prueba-firms?preset=Santa%20Cruz&days=5">Probar Santa Cruz 5 días</a>
            <a class="button light" href="/prueba-firms?preset=Bolivia&days=5">Probar Bolivia 5 días</a>
          </p>

          <div class="notice">
            Actualización automática: CampoSeguro consulta Bolivia completa como área operativa principal. No consulta Sudamérica completa para evitar ruido operativo.
          </div>
        </div>

        <div class="card">
          <h2>Resumen por fuente</h2>
          <table>
            <thead><tr><th>Fuente</th><th>Estado</th><th>Status</th><th>Filas</th><th>URL</th><th>Mensaje</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </div>

        {details}
        """
        return layout("Prueba FIRMS", body)
    except Exception as exc:
        return error_page(exc)




@app.get("/landing", response_class=HTMLResponse)
def landing():
    body = """
    <section class="hero">
      <div>
        <h2>CampoSeguro</h2>
        <p>Plataforma de alerta temprana informativa para monitorear focos de calor cercanos a zonas registradas.</p>
        <p>Diseñada para predios, comunidades, municipios, áreas protegidas y proyectos territoriales.</p>
        <p><a class="button" href="/">Entrar a la plataforma</a></p>
      </div>
      <div class="public-note">
        <strong>Funciones principales</strong><br>
        Monitoreo FIRMS, zonas con radio configurable, alertas registradas, reporte operativo y mensajes listos para comunicación preventiva.
      </div>
    </section>
    """
    return layout("CampoSeguro", body)


@app.get("/configuracion", response_class=HTMLResponse)
def configuracion():
    key_status = "Configurada" if FIRMS_MAP_KEY and FIRMS_MAP_KEY != "coloca_aqui_tu_map_key" else "Falta configurar"
    body = f"""
    <div class="card">
      <h2>Configuración actual</h2>
      <p><strong>Llave FIRMS:</strong> {esc(key_status)}</p>
      <p><strong>Región API:</strong> Sudamérica / South_America</p>
      <p><strong>Área operativa:</strong> Bolivia completa</p>
      <p><strong>BBOX base:</strong> {esc(FIRMS_AREA_BBOX)}</p>
      <p><strong>Rango de días:</strong> {esc(FIRMS_DAY_RANGE)}</p>
      <p><strong>Fuentes:</strong> {esc(FIRMS_SOURCES)}</p>
      <p><strong>Ubicación desde teléfono:</strong> disponible al crear o editar zonas.</p>
      <p><strong>Correo:</strong> EMAIL_ENABLED controla si se envían correos reales o se generan archivos outbox.</p>
      <p><strong>EMAIL_ENABLED:</strong> {esc(EMAIL_ENABLED)}</p>
      <p><strong>SMTP:</strong> {esc(SMTP_HOST or "No configurado")}:{esc(SMTP_PORT)} | SSL: {esc(SMTP_USE_SSL)} | STARTTLS: {esc(SMTP_USE_TLS)}</p>
      <p><strong>Remitente:</strong> {esc(SMTP_FROM or "No configurado")}</p>
      <p><strong>Control anti-saturación:</strong> correos desde nivel {esc(EMAIL_MIN_LEVEL)}, máximo {esc(EMAIL_MAX_PER_ZONE)} alerta(s) por zona.</p>
      <p><strong>Radio recomendado:</strong> {esc(DEFAULT_ZONE_RADIUS_KM)} km</p>
      <p><strong>Monitoreo automático:</strong> {esc("Activado" if AUTO_MONITOR_ENABLED else "Desactivado")} cada {esc(AUTO_MONITOR_INTERVAL_MINUTES)} minutos</p>
      <p><strong>Base de datos:</strong> {esc(DB_BACKEND)}</p>
      <p><strong>Acceso protegido:</strong> {esc("Activado" if AUTH_ENABLED else "Desactivado")}</p>
      <p><strong>Usuario administrador:</strong> {esc(ADMIN_USER)}</p>
      <p><strong>Usuario cliente:</strong> {esc(CLIENT_USER)}</p>
      <p><strong>Acceso cliente:</strong> {esc("Configurado" if CLIENT_PASSWORD else "Falta configurar CLIENT_PASSWORD")}</p>
      <p><strong>Contraseña admin:</strong> {esc("Configurada" if ADMIN_PASSWORD else "Falta configurar")}</p>
      <p><a class="button light" href="/prueba-firms">Abrir prueba técnica FIRMS</a></p>
      <p>Para cambiar FIRMS, edita el archivo <strong>.env</strong> y vuelve a abrir CampoSeguro.</p>
    </div>
    <div class="card">
      <h2>Limpieza de datos</h2>
      <p>Esto borra focos y alertas guardadas, pero mantiene usuarios y zonas.</p>
      <form method="post" action="/limpiar"><button class="danger" type="submit">Limpiar focos y alertas</button></form>
    </div>
    """
    return layout("Configuración", body)