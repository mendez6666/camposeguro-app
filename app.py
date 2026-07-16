from __future__ import annotations

import csv
import html
import io
import json
import threading
import time
import traceback
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse, PlainTextResponse
from starlette.middleware.sessions import SessionMiddleware

import config
import db
import emailer
import monitor

app = FastAPI(title=f"CampoSeguro v{config.APP_VERSION}")
app.add_middleware(SessionMiddleware, secret_key=config.SESSION_SECRET, same_site="lax", https_only=False)

CSS = """
:root { --green:#0f5132; --green2:#197641; --light:#eef8f1; --bg:#f3f5f4; --text:#17212b; --muted:#5b6770; --orange:#ff7a1a; --red:#b42318; --blue:#2563eb; }
* { box-sizing:border-box; }
body { margin:0; font-family:Arial, Helvetica, sans-serif; background:var(--bg); color:var(--text); }
a { color:inherit; text-decoration:none; }
.header { background:linear-gradient(100deg,#07321f,#197641); color:white; padding:16px 32px 12px; }
.brand { display:flex; align-items:center; gap:14px; }
.logo { width:74px; height:54px; object-fit:contain; }
.brand h1 { margin:0; font-size:24px; line-height:1; }
.brand p { margin:4px 0 0; font-size:13px; opacity:.92; }
.nav { background:#0b3d28; color:white; display:flex; gap:20px; padding:10px 32px; font-weight:700; font-size:14px; flex-wrap:wrap; }
.nav a { opacity:.98; }
.nav a:hover { text-decoration:underline; }
.page { padding:24px 32px 60px; }
.card { background:white; border-radius:18px; box-shadow:0 6px 20px rgba(0,0,0,.07); padding:24px; margin-bottom:20px; }
.card h2, .card h3 { margin-top:0; }
.grid { display:grid; grid-template-columns:repeat(4,minmax(160px,1fr)); gap:16px; }
.stat { background:white; border-radius:16px; box-shadow:0 6px 20px rgba(0,0,0,.06); padding:20px; }
.stat .label { color:#52616d; font-weight:700; font-size:13px; }
.stat .num { font-size:34px; font-weight:900; margin-top:8px; }
.btn { display:inline-block; border:0; background:#e6f4ec; color:#0f5132; font-weight:800; padding:12px 18px; border-radius:10px; margin:4px 6px 4px 0; cursor:pointer; font-size:14px; }
.btn.primary { background:#1b7b45; color:white; }
.btn.danger { background:#fee2e2; color:#991b1b; }
.notice { background:#fff7ed; border-left:4px solid #ff7a1a; padding:14px 16px; border-radius:10px; margin:14px 0; }
.success { background:#ecfdf5; border-left:4px solid #10b981; padding:14px 16px; border-radius:10px; margin:14px 0; }
.error { background:#fef2f2; border-left:4px solid #ef4444; padding:14px 16px; border-radius:10px; margin:14px 0; }
table { width:100%; border-collapse:collapse; font-size:14px; }
th { background:#eaf4ef; text-align:left; padding:11px; }
td { border-bottom:1px solid #e5e7eb; padding:11px; vertical-align:top; }
input, select, textarea { width:100%; padding:11px 12px; border:1px solid #cfd8dc; border-radius:9px; font-size:14px; }
label { font-weight:700; display:block; margin:10px 0 6px; }
.form-grid { display:grid; grid-template-columns:repeat(2,minmax(220px,1fr)); gap:14px; }
.badge { display:inline-block; border-radius:999px; padding:6px 10px; font-weight:900; font-size:12px; }
.badge.CRITICO { background:#fee2e2; color:#991b1b; }
.badge.ATENCION { background:#fef3c7; color:#92400e; }
.badge.INFORMATIVO { background:#dbeafe; color:#1e40af; }
.alert-card { border-left:7px solid #16a34a; }
.alert-card.CRITICO { border-left-color:#b42318; }
.alert-card.ATENCION { border-left-color:#f59e0b; }
.alert-card.INFORMATIVO { border-left-color:#2563eb; }
pre { background:#111827; color:#f9fafb; padding:18px; border-radius:12px; overflow:auto; }
.small { color:#64748b; font-size:13px; }
.login-wrap { max-width:460px; margin:60px auto; }
.map-page { padding:0; }
#map { height:calc(100vh - 122px); min-height:620px; width:100%; }
.map-panel { position:absolute; z-index:900; top:150px; left:18px; background:white; border-radius:14px; padding:14px 16px; box-shadow:0 8px 26px rgba(0,0,0,.18); min-width:185px; font-size:13px; }
.map-help { position:absolute; z-index:900; top:150px; right:18px; background:white; border-radius:14px; padding:14px 16px; box-shadow:0 8px 26px rgba(0,0,0,.18); max-width:280px; font-size:13px; }
.map-tabs { display:flex; gap:8px; margin:8px 0 10px; }
.map-tabs button { border:0; border-radius:10px; background:#e6f4ec; color:#0f5132; font-weight:800; padding:8px 12px; cursor:pointer; }
.legend-item { display:flex; align-items:center; gap:6px; margin:4px 0; }
.dot { width:11px; height:11px; border-radius:50%; display:inline-block; }
.dot.red { background:#e03131; } .dot.orange { background:#ff7a1a; } .dot.blue { background:#2563eb; }
@media (max-width:900px) { .grid { grid-template-columns:repeat(2,1fr); } .form-grid { grid-template-columns:1fr; } .nav { gap:12px; padding:10px 18px; } .page { padding:18px; } .header { padding:14px 18px; } .map-panel { top:145px; left:10px; max-width:170px; } .map-help { top:145px; right:10px; max-width:230px; } }
@media print { .nav, .btn, .header { display:none !important; } body { background:white; } .card, .stat { box-shadow:none; border:1px solid #ddd; } }
"""


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def current_user(request: Request) -> dict[str, Any] | None:
    uid = request.session.get("user_id")
    if not uid:
        return None
    return db.execute("SELECT * FROM users WHERE id=%s AND active=TRUE", (uid,), fetch="one")


def require_login(request: Request) -> dict[str, Any] | RedirectResponse:
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return user


def require_admin(request: Request) -> dict[str, Any] | RedirectResponse:
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "admin":
        return RedirectResponse("/cliente", status_code=303)
    return user


def nav_html(user: dict[str, Any] | None) -> str:
    if not user:
        return ""
    if user["role"] == "client":
        items = [
            ("/cliente", "Inicio"), ("/cliente/mapa", "Mapa"), ("/cliente/zonas", "Mis zonas"),
            ("/cliente/alertas", "Mis alertas"), ("/cliente/reporte", "Reporte"), ("/logout", "Salir"),
        ]
    else:
        items = [
            ("/", "Inicio"), ("/mapa", "Mapa"), ("/resumen", "Resumen"), ("/monitor", "Monitor"),
            ("/base-de-datos", "Base de datos"), ("/reporte", "Reporte"), ("/alertas", "Alertas"),
            ("/zonas", "Zonas"), ("/usuarios", "Usuarios"), ("/correos", "Correos"),
            ("/configuracion", "Configuración"), ("/logout", "Salir"),
        ]
    return '<div class="nav">' + ''.join(f'<a href="{esc(h)}">{esc(t)}</a>' for h, t in items) + '</div>'


def layout(title: str, body: str, user: dict[str, Any] | None = None, page_class: str = "") -> HTMLResponse:
    subtitle = "Vista cliente: seguimiento informativo de focos de calor" if user and user.get("role") == "client" else "Alerta temprana informativa de focos de calor para zonas registradas"
    head = (
        "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{esc(title)} | CampoSeguro</title><style>{CSS}</style></head><body>"
    )
    header = (
        "<div class='header'><div class='brand'>"
        f"<img class='logo' src='{esc(config.LOGO_CAMPOSEGURO_URL)}' alt='CampoSeguro'>"
        f"<div><h1>CampoSeguro</h1><p>{esc(subtitle)}</p></div>"
        "</div></div>"
    )
    page_open = f"<main class='page {esc(page_class)}'>" if page_class != "map-page" else "<main class='map-page'>"
    html_out = head + header + nav_html(user) + page_open + body + "</main></body></html>"
    return HTMLResponse(html_out)


def error_page(exc: Exception) -> HTMLResponse:
    text = traceback.format_exc()
    body = "<div class='card'><h2>Error interno CampoSeguro</h2><p>Revisar logs de Render.</p><pre>" + esc(text) + "</pre></div>"
    return layout("Error", body, None)


@app.exception_handler(Exception)
async def handle_exception(request: Request, exc: Exception):
    print("CampoSeguro internal error:", repr(exc), flush=True)
    print(traceback.format_exc(), flush=True)
    return PlainTextResponse("Error interno CampoSeguro. Revisar logs de Render.", status_code=500)


@app.on_event("startup")
def startup() -> None:
    db.init_db()
    db.seed_data()
    if config.AUTO_MONITOR_ENABLED:
        start_auto_monitor_thread()


_auto_thread_started = False


def start_auto_monitor_thread() -> None:
    global _auto_thread_started
    if _auto_thread_started:
        return
    _auto_thread_started = True

    def loop() -> None:
        time.sleep(30)
        while True:
            try:
                monitor.run_monitor("auto-web")
            except Exception as exc:
                db.set_state("status", "Error auto")
                db.set_state("last_error", repr(exc))
            time.sleep(max(60, config.MONITOR_INTERVAL_MINUTES * 60))

    threading.Thread(target=loop, daemon=True).start()


def run_monitor_background(trigger: str) -> bool:
    if db.get_state("running", "false") == "true":
        return False

    def job() -> None:
        try:
            monitor.run_monitor(trigger)
        except Exception as exc:
            db.set_state("status", "Error")
            db.set_state("last_error", repr(exc))

    threading.Thread(target=job, daemon=True).start()
    return True


@app.get("/healthz")
def healthz():
    return {"status": "ok", "app": "CampoSeguro", "version": config.APP_VERSION, "auth": True}


@app.get("/login")
def login_get(request: Request):
    body = """
    <div class="login-wrap card">
      <h2>Acceso CampoSeguro</h2>
      <p class="small">Ingresa con tu correo y contraseña/token.</p>
      <form method="post" action="/login">
        <label>Correo</label><input type="email" name="email" required>
        <label>Contraseña o token</label><input type="password" name="password" required>
        <button class="btn primary" type="submit">Ingresar</button>
      </form>
    </div>
    """
    return layout("Acceso", body, None)


@app.post("/login")
async def login_post(request: Request):
    form = await request.form()
    email = str(form.get("email", "")).strip().lower()
    password = str(form.get("password", ""))
    user = db.execute("SELECT * FROM users WHERE email=%s AND active=TRUE", (email,), fetch="one")
    ok = False
    if user:
        ok = db.check_password(password, user.get("password_hash")) or password == user.get("client_token")
    if not ok:
        body = "<div class='login-wrap card'><h2>No se pudo ingresar</h2><p>Revisa el correo y la clave.</p><a class='btn primary' href='/login'>Volver</a></div>"
        return layout("Acceso", body, None)
    request.session["user_id"] = int(user["id"])
    if user["role"] == "admin":
        return RedirectResponse("/", status_code=303)
    return RedirectResponse("/cliente", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


def counts_for(user_id: int | None = None) -> dict[str, int]:
    if user_id:
        users = 1
        zones = db.execute("SELECT COUNT(*) AS n FROM zones WHERE user_id=%s AND active=TRUE", (user_id,), fetch="one")["n"]
        alerts = db.execute("SELECT COUNT(*) AS n FROM zone_alerts WHERE user_id=%s AND active=TRUE", (user_id,), fetch="one")["n"]
        critical = db.execute("SELECT COUNT(*) AS n FROM zone_alerts WHERE user_id=%s AND active=TRUE AND level='CRITICO'", (user_id,), fetch="one")["n"]
    else:
        users = db.execute("SELECT COUNT(*) AS n FROM users WHERE active=TRUE AND role='client'", fetch="one")["n"]
        zones = db.execute("SELECT COUNT(*) AS n FROM zones WHERE active=TRUE", fetch="one")["n"]
        alerts = db.execute("SELECT COUNT(*) AS n FROM zone_alerts WHERE active=TRUE", fetch="one")["n"]
        critical = db.execute("SELECT COUNT(*) AS n FROM zone_alerts WHERE active=TRUE AND level='CRITICO'", fetch="one")["n"]
    focos = db.execute("SELECT COUNT(*) AS n FROM focos", fetch="one")["n"]
    return {"users": int(users), "zones": int(zones), "focos": int(focos), "alerts": int(alerts), "critical": int(critical)}


def stats_grid(stats: dict[str, int], client: bool = False) -> str:
    labels = [
        ("Usuarios activos" if not client else "Mis zonas monitoreadas", stats["users"] if not client else stats["zones"]),
        ("Zonas activas" if not client else "Focos asociados", stats["zones"] if not client else stats["focos"]),
        ("Focos FIRMS" if not client else "Zonas con alerta", stats["focos"] if not client else stats["alerts"]),
        ("Zonas con alerta" if not client else "Críticas", stats["alerts"] if not client else stats["critical"]),
        ("Críticas", stats["critical"]),
    ] if not client else [
        ("Mis zonas monitoreadas", stats["zones"]), ("Focos FIRMS", stats["focos"]), ("Mis zonas con alerta", stats["alerts"]), ("Críticas", stats["critical"])
    ]
    return '<div class="grid">' + ''.join(f"<div class='stat'><div class='label'>{esc(k)}</div><div class='num'>{esc(v)}</div></div>" for k, v in labels) + '</div>'


@app.get("/")
def inicio(request: Request):
    user = require_login(request)
    if isinstance(user, RedirectResponse):
        return user
    if user["role"] == "client":
        return RedirectResponse("/cliente", status_code=303)
    stats = counts_for()
    state = db.all_state()
    body = f"""
    <div class='card'>
      <h2>Monitoreo de fuego cercano</h2>
      <p>Registra usuarios y zonas de interés. CampoSeguro consulta FIRMS y prioriza alertas agrupadas por zona.</p>
      <a class='btn primary' href='/actualizar'>Actualizar monitoreo</a>
      <a class='btn' href='/mapa'>Ver mapa</a>
      <a class='btn' href='/usuarios'>Usuarios</a>
      <a class='btn' href='/zonas'>Zonas</a>
      <a class='btn' href='/monitor'>Monitor automático</a>
      <a class='btn' href='/reporte'>Reporte operativo</a>
      <a class='btn' href='/correos'>Correos</a>
      <div class='success'><b>Estado del sistema</b><br>
      Llave FIRMS: {'Configurada' if config.FIRMS_MAP_KEY else 'Pendiente'}<br>
      Región API: Sudamérica / South_America<br>
      Área operativa: Bolivia<br>
      Evaluación de alertas: últimos {esc(config.FIRMS_DAY_RANGE)} días<br>
      Monitor automático: {'Activo' if config.AUTO_MONITOR_ENABLED else 'Desactivado'} / cada {esc(config.MONITOR_INTERVAL_MINUTES)} min<br>
      Base de datos: postgresql<br>
      Último estado: {esc(state.get('status',''))}</div>
    </div>
    """ + stats_grid(stats) + """
    <div class='card'><h3>Distribución de zonas con alerta</h3>__DIST__<div class='notice'>CampoSeguro es informativo. No reemplaza verificación en campo ni sistemas oficiales.</div></div>
    """
    dist = alert_distribution_html()
    return layout("Inicio", body.replace("__DIST__", dist), user)


def alert_distribution_html(user_id: int | None = None) -> str:
    params = []
    where = "WHERE active=TRUE"
    if user_id:
        where += " AND user_id=%s"
        params.append(user_id)
    rows = db.execute(f"SELECT level, COUNT(*) AS n FROM zone_alerts {where} GROUP BY level", tuple(params), fetch="all") or []
    d = {r["level"]: int(r["n"]) for r in rows}
    return (
        f"<span class='badge CRITICO'>Críticas: {d.get('CRITICO',0)}</span> "
        f"<span class='badge ATENCION'>Atención: {d.get('ATENCION',0)}</span> "
        f"<span class='badge INFORMATIVO'>Informativas: {d.get('INFORMATIVO',0)}</span>"
    )


@app.get("/cliente")
def cliente_inicio(request: Request):
    user = require_login(request)
    if isinstance(user, RedirectResponse):
        return user
    if user["role"] == "admin":
        return RedirectResponse("/", status_code=303)
    stats = counts_for(user["id"])
    body = """
    <div class='card'>
      <h2>Panel de seguimiento</h2>
      <p>Consulta tu mapa, ajusta radios de alerta, revisa alertas registradas y descarga un reporte operativo simple.</p>
      <a class='btn primary' href='/cliente/mapa'>Ver mapa</a>
      <a class='btn' href='/cliente/zonas'>Ajustar radios</a>
      <a class='btn' href='/cliente/alertas'>Ver alertas</a>
      <a class='btn' href='/cliente/reporte'>Ver reporte</a>
    </div>
    <div class='notice'>Vista filtrada por tu usuario. Solo ves tus zonas y alertas.</div>
    """ + stats_grid(stats, client=True) + "<div class='notice'>CampoSeguro es una herramienta informativa. No reemplaza verificación en campo ni sistemas oficiales de emergencia.</div>"
    return layout("Cliente", body, user)


def _to_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _valid_latlon(lat: float | None, lon: float | None) -> bool:
    return lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180


def map_data(user_id: int | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    # Mapa tolerante a migraciones: si alguna tabla vieja tiene columnas raras,
    # no debe tumbar toda la app. El error queda impreso en Render Logs.
    if user_id:
        zones_raw = db.execute(
            """
            SELECT z.*, a.level, a.foco_count, a.min_distance_km
            FROM zones z LEFT JOIN zone_alerts a ON a.zone_id=z.id
            WHERE z.user_id=%s AND z.active=TRUE
            ORDER BY z.name
            """,
            (user_id,), fetch="all") or []
    else:
        zones_raw = db.execute(
            """
            SELECT z.*, u.name AS user_name, a.level, a.foco_count, a.min_distance_km
            FROM zones z JOIN users u ON u.id=z.user_id
            LEFT JOIN zone_alerts a ON a.zone_id=z.id
            WHERE z.active=TRUE
            ORDER BY u.name, z.name
            """,
            fetch="all") or []

    zones: list[dict[str, Any]] = []
    for zrow in zones_raw:
        z = dict(zrow)
        lat = _to_float(z.get("lat") or z.get("latitude") or z.get("latitud"))
        lon = _to_float(z.get("lon") or z.get("longitude") or z.get("longitud"))
        if not _valid_latlon(lat, lon):
            continue
        z["lat"] = lat
        z["lon"] = lon
        z["radius_km"] = _to_float(z.get("radius_km"), config.DEFAULT_ZONE_RADIUS_KM) or config.DEFAULT_ZONE_RADIUS_KM
        if z.get("foco_count") is None:
            z["foco_count"] = 0
        zones.append(z)

    focos_raw = []
    try:
        # Importante: versiones anteriores guardaban coordenadas como
        # latitude/longitude o latitud/longitud. No filtramos por lat/lon
        # porque esas columnas pueden existir pero estar vacías después de migrar.
        focos_raw = db.execute(
            """
            SELECT *
            FROM focos
            ORDER BY id DESC
            LIMIT 6000
            """,
            fetch="all") or []
    except Exception as exc:
        print("CampoSeguro map focos query error:", repr(exc), flush=True)
        print(traceback.format_exc(), flush=True)
        try:
            focos_raw = db.execute("SELECT * FROM focos ORDER BY id DESC LIMIT 6000", fetch="all") or []
        except Exception as exc2:
            print("CampoSeguro map focos fallback error:", repr(exc2), flush=True)
            print(traceback.format_exc(), flush=True)
            focos_raw = []

    focos: list[dict[str, Any]] = []
    for frow in focos_raw:
        f0 = dict(frow)
        raw = f0.get("raw")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = {}
        if not isinstance(raw, dict):
            raw = {}
        lat = _to_float(f0.get("lat") or f0.get("latitude") or f0.get("latitud") or raw.get("latitude") or raw.get("latitud"))
        lon = _to_float(f0.get("lon") or f0.get("longitude") or f0.get("longitud") or raw.get("longitude") or raw.get("longitud"))
        if not _valid_latlon(lat, lon):
            continue
        source = f0.get("source") or f0.get("fuente") or f0.get("satellite") or raw.get("fuente") or raw.get("satellite") or "FIRMS"
        focos.append({
            "id": f0.get("id"),
            "source": str(source),
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "acq_date": str(f0.get("acq_date") or f0.get("date") or raw.get("acq_date") or raw.get("fecha") or ""),
            "acq_time": str(f0.get("acq_time") or f0.get("time") or raw.get("acq_time") or raw.get("hora") or ""),
        })

    try:
        if user_id:
            alerts_raw = db.execute("SELECT * FROM zone_alerts WHERE user_id=%s AND active=TRUE", (user_id,), fetch="all") or []
        else:
            alerts_raw = db.execute("SELECT * FROM zone_alerts WHERE active=TRUE", fetch="all") or []
    except Exception as exc:
        print("CampoSeguro map alerts query error:", repr(exc), flush=True)
        print(traceback.format_exc(), flush=True)
        alerts_raw = []
    return zones, focos, [dict(a) for a in alerts_raw]


def map_page_html(user: dict[str, Any], user_id: int | None = None) -> HTMLResponse:
    map_error = ""
    try:
        zones, focos, alerts = map_data(user_id)
    except Exception as exc:
        trace = traceback.format_exc()
        print("CampoSeguro map_page_html error:", repr(exc), flush=True)
        print(trace, flush=True)
        zones, focos, alerts = [], [], []
        map_error = "<div class='error' style='position:absolute;z-index:999;left:20px;right:20px;top:20px'>No se pudo cargar la información del mapa. Revisa Render Logs.</div>"
    title_text = "Vista cliente" if user_id else "CampoSeguro"
    panel = f"""
    <div class='map-panel'>
      <b>CampoSeguro</b><br>{esc(title_text)}<br>
      Zonas: {len(zones)}<br>Focos FIRMS: {len(focos)}<br>Zonas con alerta: {len(alerts)}
      <hr>
      <div class='legend-item'><span class='dot blue'></span>Zona monitoreada</div>
      <div class='legend-item'><span class='dot orange'></span>Foco MODIS</div>
      <div class='legend-item'><span class='dot red'></span>Foco VIIRS</div>
      <button class='btn' style='padding:8px 12px;margin-top:8px' onclick='showAll()'>Todo</button>
    </div>
    <div class='map-help'><b>Vista del mapa</b><div class='map-tabs'><button onclick='showZones()'>Zonas</button><button onclick='showFocos()'>Focos</button><button onclick='showAll()'>Todo</button></div>
    <p class='small'>Las alertas se calculan por zona según el radio configurado. Los puntos FIRMS son contexto satelital.</p></div>
    <div id='map'></div>
    """
    js = """
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
    const zones = __ZONES__;
    const focos = __FOCOS__;
    const map = L.map('map', { zoomControl:false, preferCanvas:true }).setView([-17.8,-63.1], 6);
    L.control.zoom({position:'bottomright'}).addTo(map);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, attribution: '© OpenStreetMap' }).addTo(map);
    const zoneLayer = L.layerGroup().addTo(map);
    const focoLayer = L.layerGroup().addTo(map);
    const bounds = [];
    const focoBounds = [];
    function levelColor(level){ if(level==='CRITICO') return '#b42318'; if(level==='ATENCION') return '#f59e0b'; return '#2563eb'; }
    zones.forEach(z => {
      const color = levelColor(z.level || 'INFORMATIVO');
      const circle = L.circle([z.lat,z.lon], {radius:(z.radius_km||15)*1000, color:color, fillColor:color, fillOpacity:0.08, weight:3});
      circle.bindPopup(`<b>${z.name || 'Zona'}</b><br>Municipio: ${z.municipio||''}<br>Radio: ${z.radius_km} km<br>Nivel: ${z.level||'Sin alerta'}<br>Focos dentro del radio: ${z.foco_count||0}`);
      circle.addTo(zoneLayer);
      L.circleMarker([z.lat,z.lon], {radius:6, color:'#0f5132', fillColor:'#2563eb', fillOpacity:0.9}).addTo(zoneLayer);
      bounds.push([z.lat,z.lon]);
    });
    focos.forEach(f => {
      const lat = Number(f.lat);
      const lon = Number(f.lon);
      if(!Number.isFinite(lat) || !Number.isFinite(lon)) return;
      const isModis = (f.source||'').includes('MODIS');
      const color = isModis ? '#ff7a1a' : '#e03131';
      const m = L.circleMarker([lat,lon], {radius:3, color:color, fillColor:color, fillOpacity:0.65, weight:1});
      m.bindPopup(`<b>Foco FIRMS</b><br>Fuente: ${f.source||''}<br>Fecha: ${f.acq_date||''} ${f.acq_time||''}<br>${lat.toFixed(5)}, ${lon.toFixed(5)}`);
      m.addTo(focoLayer);
      focoBounds.push([lat,lon]);
    });
    if(bounds.length){ map.fitBounds(bounds, {padding:[60,60]}); }
    function showZones(){ if(!map.hasLayer(zoneLayer)) map.addLayer(zoneLayer); if(map.hasLayer(focoLayer)) map.removeLayer(focoLayer); if(bounds.length){ map.fitBounds(bounds, {padding:[60,60]}); } }
    function showFocos(){ if(map.hasLayer(zoneLayer)) map.removeLayer(zoneLayer); if(!map.hasLayer(focoLayer)) map.addLayer(focoLayer); if(focoBounds.length){ map.fitBounds(focoBounds, {padding:[40,40]}); } }
    function showAll(){ if(!map.hasLayer(zoneLayer)) map.addLayer(zoneLayer); if(!map.hasLayer(focoLayer)) map.addLayer(focoLayer); const allBounds = bounds.concat(focoBounds); if(allBounds.length){ map.fitBounds(allBounds, {padding:[40,40]}); } }
    </script>
    """.replace("__ZONES__", json.dumps(zones, default=str, ensure_ascii=False)).replace("__FOCOS__", json.dumps(focos, default=str, ensure_ascii=False))
    return layout("Mapa", map_error + panel + js, user, "map-page")


@app.get("/mapa")
def mapa(request: Request):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user
    return map_page_html(user, None)


@app.get("/cliente/mapa")
def cliente_mapa(request: Request):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user
    if user["role"] == "admin": return RedirectResponse("/mapa", status_code=303)
    return map_page_html(user, user["id"])


@app.get("/actualizar")
def actualizar(request: Request):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user
    run_monitor_background("manual-web")
    return RedirectResponse("/monitor", status_code=303)


@app.get("/monitor")
def monitor_page(request: Request):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user
    s = db.all_state()
    body = f"""
    <div class='card'><h2>Monitoreo automático</h2>
    <p><b>Estado:</b> {esc(s.get('status',''))}</p>
    <p><b>Activo:</b> {'Sí' if config.AUTO_MONITOR_ENABLED else 'No'}</p>
    <p><b>Ejecutándose ahora:</b> {'Sí' if s.get('running') == 'true' else 'No'}</p>
    <p><b>Intervalo:</b> cada {esc(config.MONITOR_INTERVAL_MINUTES)} minutos</p>
    <p><b>Última ejecución UTC:</b> {esc(s.get('last_run_utc','Pendiente'))}</p>
    <p><b>Último disparador:</b> {esc(s.get('last_trigger',''))}</p><hr>
    <p><b>Focos descargados:</b> {esc(s.get('last_downloaded','0'))}</p>
    <p><b>Focos nuevos guardados:</b> {esc(s.get('last_new_focos','0'))}</p>
    <p><b>Zonas con alerta recalculadas:</b> {esc(s.get('last_alert_zones','0'))}</p>
    <p><b>Correos resumen encolados:</b> {esc(s.get('last_daily_queued','0'))}</p>
    <p><b>Correos urgentes encolados:</b> {esc(s.get('last_urgent_queued','0'))}</p>
    <p><b>Correos enviados:</b> {esc(s.get('last_email_sent','0'))} | <b>errores:</b> {esc(s.get('last_email_errors','0'))}</p>
    <p><b>Último error:</b> {esc(s.get('last_error',''))}</p>
    </div>
    <div class='card'><h3>Acciones</h3><a class='btn primary' href='/actualizar'>Ejecutar monitoreo ahora</a><a class='btn' href='/correos'>Ver correos</a><a class='btn' href='/reporte'>Ver reporte</a></div>
    """
    return layout("Monitor", body, user)


def alerts_query(user_id: int | None = None):
    if user_id:
        return db.execute(
            """
            SELECT a.*, z.name AS zone_name, z.municipio, z.radius_km, u.name AS user_name, u.phone, f.lat AS foco_lat, f.lon AS foco_lon, f.source, f.acq_date, f.acq_time
            FROM zone_alerts a JOIN zones z ON z.id=a.zone_id JOIN users u ON u.id=a.user_id LEFT JOIN focos f ON f.id=a.nearest_foco_id
            WHERE a.user_id=%s AND a.active=TRUE
            ORDER BY CASE a.level WHEN 'CRITICO' THEN 3 WHEN 'ATENCION' THEN 2 ELSE 1 END DESC, a.min_distance_km ASC
            """, (user_id,), fetch="all") or []
    return db.execute(
        """
        SELECT a.*, z.name AS zone_name, z.municipio, z.radius_km, u.name AS user_name, u.phone, f.lat AS foco_lat, f.lon AS foco_lon, f.source, f.acq_date, f.acq_time
        FROM zone_alerts a JOIN zones z ON z.id=a.zone_id JOIN users u ON u.id=a.user_id LEFT JOIN focos f ON f.id=a.nearest_foco_id
        WHERE a.active=TRUE
        ORDER BY CASE a.level WHEN 'CRITICO' THEN 3 WHEN 'ATENCION' THEN 2 ELSE 1 END DESC, a.min_distance_km ASC
        """, fetch="all") or []


def alerts_cards(rows) -> str:
    if not rows:
        return "<div class='card'><p>No hay alertas registradas.</p></div>"
    out = []
    for a in rows:
        google = "#"
        if a.get("foco_lat") is not None:
            google = f"https://www.google.com/maps?q={a['foco_lat']},{a['foco_lon']}"
        out.append(f"""
        <div class='card alert-card {esc(a['level'])}'>
          <h2>{esc(a['zone_name'])} <span class='badge {esc(a['level'])}'>{esc(a['level'])}</span></h2>
          <div class='grid'>
            <div><b>Usuario</b><br>{esc(a.get('user_name'))}</div><div><b>Municipio</b><br>{esc(a.get('municipio'))}</div>
            <div><b>Focos dentro del radio</b><br>{esc(a.get('foco_count'))}</div><div><b>Distancia mínima</b><br>{float(a.get('min_distance_km') or 0):.2f} km</div>
            <div><b>Radio configurado</b><br>{float(a.get('radius_km') or 0):.1f} km</div><div><b>Fuente</b><br>{esc(a.get('source'))}</div>
            <div><b>Última detección</b><br>{esc(a.get('latest_detection'))}</div><div><b>Teléfono</b><br>{esc(a.get('phone'))}</div>
          </div>
          <p class='notice'>{esc(a.get('message'))}</p>
          <a class='btn primary' href='{esc(google)}' target='_blank'>Abrir foco priorizado en Google Maps</a>
        </div>
        """)
    return ''.join(out)


@app.get("/alertas")
def alertas(request: Request):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user
    body = "<div class='card'><h2>Panel de alertas</h2><p>Alertas agrupadas por zona, prioridad y distancia mínima.</p></div>" + alerts_cards(alerts_query())
    return layout("Alertas", body, user)


@app.get("/cliente/alertas")
def cliente_alertas(request: Request):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user
    if user["role"] == "admin": return RedirectResponse("/alertas", status_code=303)
    body = "<div class='card'><h2>Mis alertas</h2><p>Alertas informativas generadas por cercanía de focos de calor a tus zonas monitoreadas.</p><div class='notice'>Vista filtrada por tu usuario.</div></div>" + alerts_cards(alerts_query(user["id"]))
    return layout("Mis alertas", body, user)


def zones_table(rows, client=False) -> str:
    if not rows:
        return "<p>No hay zonas registradas.</p>"
    out = ["<table><thead><tr><th>Zona</th><th>Usuario</th><th>Municipio</th><th>Coordenadas</th><th>Radio actual</th><th>Nuevo radio</th></tr></thead><tbody>"]
    action = "/cliente/zonas/radio" if client else "/zonas/radio"
    for z in rows:
        out.append(f"""
        <tr><td><b>{esc(z['name'])}</b></td><td>{esc(z.get('user_name',''))}</td><td>{esc(z.get('municipio',''))}</td>
        <td>{float(z['lat']):.5f}, {float(z['lon']):.5f}</td><td>{float(z['radius_km']):.1f} km</td>
        <td><form method='post' action='{action}' style='display:flex;gap:8px;align-items:center'>
        <input type='hidden' name='zone_id' value='{esc(z['id'])}'><select name='radius_km'>
        {''.join(f"<option value='{r}' {'selected' if int(round(float(z['radius_km'])))==r else ''}>{r} km</option>" for r in [3,5,10,15,20,25,30,40,50])}
        </select><button class='btn primary' type='submit'>Guardar</button></form></td></tr>
        """)
    out.append("</tbody></table>")
    return ''.join(out)


@app.get("/zonas")
def zonas(request: Request):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user
    rows = db.execute("SELECT z.*, u.name AS user_name FROM zones z JOIN users u ON u.id=z.user_id ORDER BY u.name,z.name", fetch="all") or []
    body = "<div class='card'><h2>Zonas monitoreadas</h2><a class='btn primary' href='/zonas/nueva'>Nueva zona</a><div class='notice'>Cambiar el radio recalcula las alertas de zona sin descargar nuevamente FIRMS.</div>" + zones_table(rows) + "</div>"
    return layout("Zonas", body, user)


@app.get("/cliente/zonas")
def cliente_zonas(request: Request):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user
    if user["role"] == "admin": return RedirectResponse("/zonas", status_code=303)
    rows = db.execute("SELECT z.*, %s AS user_name FROM zones z WHERE z.user_id=%s ORDER BY z.name", (user["name"], user["id"]), fetch="all") or []
    body = "<div class='card'><h2>Mis zonas</h2><p>Ajusta el radio de alerta de cada zona. Un radio más corto reduce alertas lejanas y evita saturar el correo.</p><div class='notice'>Recomendación inicial: 15 km. Para predios pequeños: 3 a 10 km. Para municipios o áreas grandes: 15 a 30 km.</div>" + zones_table(rows, client=True) + "</div>"
    return layout("Mis zonas", body, user)


async def update_zone_radius(request: Request, client: bool):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user
    form = await request.form()
    zone_id = int(form.get("zone_id"))
    radius = float(form.get("radius_km"))
    if client:
        db.execute("UPDATE zones SET radius_km=%s WHERE id=%s AND user_id=%s", (radius, zone_id, user["id"]))
    else:
        if user["role"] != "admin": return RedirectResponse("/cliente", status_code=303)
        db.execute("UPDATE zones SET radius_km=%s WHERE id=%s", (radius, zone_id))
    monitor.recalc_alerts()
    return RedirectResponse("/cliente/zonas" if client else "/zonas", status_code=303)


@app.post("/zonas/radio")
async def zonas_radio(request: Request):
    return await update_zone_radius(request, False)


@app.post("/cliente/zonas/radio")
async def cliente_zonas_radio(request: Request):
    return await update_zone_radius(request, True)


@app.get("/usuarios")
def usuarios(request: Request):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user
    rows = db.execute("SELECT u.*, (SELECT COUNT(*) FROM zones z WHERE z.user_id=u.id) AS zones_count FROM users u ORDER BY role,name", fetch="all") or []
    body = "<div class='card'><h2>Usuarios y responsables</h2><a class='btn primary' href='/usuarios/nuevo'>Nuevo usuario</a><div class='notice'>Cada cliente ingresa con su correo y contraseña/token. Ya no se usa CLIENT_USER_ID para separar clientes.</div><table><thead><tr><th>ID</th><th>Nombre</th><th>Correo</th><th>Rol</th><th>Zonas</th><th>Acceso</th><th>Acción</th></tr></thead><tbody>"
    for r in rows:
        acceso = f"Correo: {r['email']}<br>Token: {str(r['client_token'])[:8]}..."
        body += f"<tr><td>{r['id']}</td><td>{esc(r['name'])}<br><span class='small'>{esc(r['organization'])}</span></td><td>{esc(r['email'])}</td><td>{esc(r['role'])}</td><td>{esc(r['zones_count'])}</td><td>{acceso}</td><td><a class='btn' href='/usuarios/{r['id']}/editar'>Editar</a></td></tr>"
    body += "</tbody></table></div>"
    return layout("Usuarios", body, user)


@app.get("/usuarios/nuevo")
def usuario_nuevo(request: Request):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user
    body = """
    <div class='card'><h2>Nuevo usuario</h2><form method='post' action='/usuarios/nuevo'>
    <div class='form-grid'><div><label>Nombre</label><input name='name' required></div><div><label>Organización</label><input name='organization'></div>
    <div><label>Correo</label><input type='email' name='email' required></div><div><label>Teléfono</label><input name='phone'></div>
    <div><label>Rol</label><select name='role'><option value='client'>Cliente</option><option value='admin'>Administrador</option></select></div>
    <div><label>Contraseña inicial</label><input name='password' value='demo123'></div></div>
    <button class='btn primary' type='submit'>Crear usuario</button></form></div>
    """
    return layout("Nuevo usuario", body, user)


@app.post("/usuarios/nuevo")
async def usuario_nuevo_post(request: Request):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user
    form = await request.form()
    import secrets
    db.execute("""
        INSERT INTO users(name, organization, email, phone, role, password_hash, client_token)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
    """, (str(form.get('name','')), str(form.get('organization','')), str(form.get('email','')).lower(), str(form.get('phone','')), str(form.get('role','client')), db.password_hash(str(form.get('password','demo123'))), secrets.token_urlsafe(24)))
    return RedirectResponse("/usuarios", status_code=303)


@app.get("/usuarios/{user_id}/editar")
def usuario_editar(request: Request, user_id: int):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user
    r = db.execute("SELECT * FROM users WHERE id=%s", (user_id,), fetch="one")
    if not r: return layout("Usuario", "<div class='card'><p>No encontrado.</p></div>", user)
    body = f"""
    <div class='card'><h2>Editar usuario</h2><form method='post' action='/usuarios/{user_id}/editar'>
    <div class='form-grid'><div><label>Nombre</label><input name='name' value='{esc(r['name'])}' required></div><div><label>Organización</label><input name='organization' value='{esc(r['organization'])}'></div>
    <div><label>Correo</label><input type='email' name='email' value='{esc(r['email'])}' required></div><div><label>Teléfono</label><input name='phone' value='{esc(r['phone'])}'></div>
    <div><label>Rol</label><select name='role'><option value='client' {'selected' if r['role']=='client' else ''}>Cliente</option><option value='admin' {'selected' if r['role']=='admin' else ''}>Administrador</option></select></div>
    <div><label>Nueva contraseña opcional</label><input name='password' placeholder='Dejar vacío para mantener'></div></div>
    <div class='notice'><b>Token de acceso:</b> {esc(r['client_token'])}</div>
    <button class='btn primary' type='submit'>Guardar</button></form></div>
    """
    return layout("Editar usuario", body, user)


@app.post("/usuarios/{user_id}/editar")
async def usuario_editar_post(request: Request, user_id: int):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user
    form = await request.form()
    password = str(form.get('password','')).strip()
    db.execute("UPDATE users SET name=%s, organization=%s, email=%s, phone=%s, role=%s WHERE id=%s", (str(form.get('name','')), str(form.get('organization','')), str(form.get('email','')).lower(), str(form.get('phone','')), str(form.get('role','client')), user_id))
    if password:
        db.execute("UPDATE users SET password_hash=%s WHERE id=%s", (db.password_hash(password), user_id))
    return RedirectResponse("/usuarios", status_code=303)


@app.get("/zonas/nueva")
def zona_nueva(request: Request):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user
    users = db.execute("SELECT id,name,email FROM users WHERE role='client' AND active=TRUE ORDER BY name", fetch="all") or []
    opts = ''.join(f"<option value='{u['id']}'>{esc(u['name'])} — {esc(u['email'])}</option>" for u in users)
    body = f"""
    <div class='card'><h2>Nueva zona</h2><form method='post' action='/zonas/nueva'>
    <div class='form-grid'><div><label>Usuario</label><select name='user_id'>{opts}</select></div><div><label>Nombre de zona</label><input name='name' required></div>
    <div><label>Municipio</label><input name='municipio'></div><div><label>Radio km</label><input name='radius_km' value='{config.DEFAULT_ZONE_RADIUS_KM}'></div>
    <div><label>Latitud</label><input name='lat' required></div><div><label>Longitud</label><input name='lon' required></div></div>
    <button class='btn primary' type='submit'>Crear zona</button></form></div>
    """
    return layout("Nueva zona", body, user)


@app.post("/zonas/nueva")
async def zona_nueva_post(request: Request):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user
    form = await request.form()
    db.execute("INSERT INTO zones(user_id,name,municipio,lat,lon,radius_km) VALUES (%s,%s,%s,%s,%s,%s)", (int(form.get('user_id')), str(form.get('name','')), str(form.get('municipio','')), float(form.get('lat')), float(form.get('lon')), float(form.get('radius_km'))))
    monitor.recalc_alerts()
    return RedirectResponse("/zonas", status_code=303)


def report_rows(user_id: int | None = None):
    if user_id:
        return db.execute("""
            SELECT z.name AS zone_name, z.municipio, u.name AS user_name, COALESCE(a.foco_count,0) AS foco_count,
                   COALESCE(a.level,'SIN ALERTA') AS level, a.min_distance_km, a.latest_detection
            FROM zones z JOIN users u ON u.id=z.user_id LEFT JOIN zone_alerts a ON a.zone_id=z.id
            WHERE z.user_id=%s AND z.active=TRUE ORDER BY CASE COALESCE(a.level,'') WHEN 'CRITICO' THEN 3 WHEN 'ATENCION' THEN 2 WHEN 'INFORMATIVO' THEN 1 ELSE 0 END DESC, a.min_distance_km ASC NULLS LAST, z.name
        """, (user_id,), fetch="all") or []
    return db.execute("""
        SELECT z.name AS zone_name, z.municipio, u.name AS user_name, COALESCE(a.foco_count,0) AS foco_count,
               COALESCE(a.level,'SIN ALERTA') AS level, a.min_distance_km, a.latest_detection
        FROM zones z JOIN users u ON u.id=z.user_id LEFT JOIN zone_alerts a ON a.zone_id=z.id
        WHERE z.active=TRUE ORDER BY CASE COALESCE(a.level,'') WHEN 'CRITICO' THEN 3 WHEN 'ATENCION' THEN 2 WHEN 'INFORMATIVO' THEN 1 ELSE 0 END DESC, a.min_distance_km ASC NULLS LAST, u.name,z.name
    """, fetch="all") or []


def report_html(user: dict[str, Any], user_id: int | None = None) -> HTMLResponse:
    stats = counts_for(user_id)
    rows = report_rows(user_id)
    csv_url = "/cliente/reporte/csv" if user_id else "/reporte/csv"
    body = f"""
    <div class='card'><h2>Reporte operativo CampoSeguro</h2><p>Monitoreo informativo de focos de calor cercanos a zonas registradas.</p>
    <button class='btn primary' onclick='window.print()'>Imprimir / Guardar PDF</button><a class='btn' href='{csv_url}'>Exportar alertas CSV</a><a class='btn' href='/mapa'>Ver mapa</a></div>
    {stats_grid(stats, client=bool(user_id))}
    <div class='card'><h3>Resumen por zona</h3><table><thead><tr><th>Zona</th><th>Usuario</th><th>Municipio</th><th>Focos dentro del radio</th><th>Nivel máximo</th><th>Distancia mínima</th><th>Última detección</th></tr></thead><tbody>
    """
    for r in rows:
        level = r["level"] if r["level"] != "SIN ALERTA" else "INFORMATIVO"
        dist = "" if r.get("min_distance_km") is None else f"{float(r['min_distance_km']):.2f} km"
        body += f"<tr><td>{esc(r['zone_name'])}</td><td>{esc(r['user_name'])}</td><td>{esc(r['municipio'])}</td><td>{esc(r['foco_count'])}</td><td><span class='badge {esc(level)}'>{esc(r['level'])}</span></td><td>{esc(dist)}</td><td>{esc(r.get('latest_detection',''))}</td></tr>"
    body += "</tbody></table><div class='notice'>CampoSeguro es una herramienta informativa. No reemplaza verificación en campo ni sistemas oficiales de emergencia.</div></div>"
    return layout("Reporte", body, user)


@app.get("/reporte")
def reporte(request: Request):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user
    return report_html(user)


@app.get("/cliente/reporte")
def cliente_reporte(request: Request):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user
    if user["role"] == "admin": return RedirectResponse("/reporte", status_code=303)
    return report_html(user, user["id"])


def csv_response(rows, filename: str):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["zona", "usuario", "municipio", "focos_dentro_radio", "nivel", "distancia_minima_km", "ultima_deteccion"])
    for r in rows:
        writer.writerow([r["zone_name"], r["user_name"], r["municipio"], r["foco_count"], r["level"], r.get("min_distance_km") or "", r.get("latest_detection") or ""])
    data = out.getvalue().encode("utf-8-sig")
    return StreamingResponse(io.BytesIO(data), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.get("/reporte/csv")
def reporte_csv(request: Request):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user
    return csv_response(report_rows(), "camposeguro_reporte_alertas.csv")


@app.get("/cliente/reporte/csv")
def cliente_reporte_csv(request: Request):
    user = require_login(request)
    if isinstance(user, RedirectResponse): return user
    return csv_response(report_rows(user["id"]), "camposeguro_reporte_cliente.csv")


@app.get("/resumen")
def resumen(request: Request):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user
    body = "<div class='card'><h2>Resumen ejecutivo</h2>" + alert_distribution_html() + "</div>"
    body += "<div class='card'><h3>Resumen por zona</h3><table><thead><tr><th>Zona</th><th>Usuario</th><th>Municipio</th><th>Zonas con alerta/Focos</th><th>Nivel</th><th>Distancia mínima</th></tr></thead><tbody>"
    for r in report_rows():
        if int(r["foco_count"]) <= 0:
            continue
        lvl = r["level"]
        body += f"<tr><td>{esc(r['zone_name'])}</td><td>{esc(r['user_name'])}</td><td>{esc(r['municipio'])}</td><td>{esc(r['foco_count'])}</td><td><span class='badge {esc(lvl)}'>{esc(lvl)}</span></td><td>{float(r['min_distance_km']):.2f} km</td></tr>"
    body += "</tbody></table></div>"
    return layout("Resumen", body, user)


@app.get("/correos")
def correos(request: Request):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user
    counts = db.execute("SELECT status, COUNT(*) AS n FROM email_outbox GROUP BY status", fetch="all") or []
    d = {r["status"]: int(r["n"]) for r in counts}
    rows = db.execute("SELECT * FROM email_outbox ORDER BY created_at DESC LIMIT 40", fetch="all") or []
    body = f"""
    <div class='card'><h2>Correos de alerta</h2><p>Estado: {'Envío real activo' if config.EMAIL_ENABLED else 'Modo seguro/local'}</p>
    <div class='grid'><div class='stat'><div class='label'>Pendientes</div><div class='num'>{d.get('queued',0)}</div></div><div class='stat'><div class='label'>Enviados</div><div class='num'>{d.get('sent',0)}</div></div><div class='stat'><div class='label'>Errores</div><div class='num'>{d.get('error',0)}</div></div><div class='stat'><div class='label'>Total histórico</div><div class='num'>{sum(d.values())}</div></div></div>
    <a class='btn primary' href='/correos/preparar'>Preparar correos</a><a class='btn primary' href='/correos/enviar'>Procesar pendientes</a><a class='btn danger' href='/correos/limpiar-pruebas'>Limpiar pruebas/errores</a>
    <div class='notice'>Modo anti-saturación: máximo un resumen diario por destinatario; urgencias críticas con enfriamiento de {config.EMAIL_URGENT_COOLDOWN_HOURS} horas.</div></div>
    <div class='card'><h3>Prueba de correo Resend</h3><p><b>EMAIL_ENABLED:</b> {esc(config.EMAIL_ENABLED)}</p><p><b>Proveedor:</b> {esc(config.EMAIL_PROVIDER)}</p><p><b>Remitente:</b> {esc(config.EMAIL_FROM)}</p><p><b>Reply-To:</b> {esc(config.EMAIL_REPLY_TO)}</p>
    <form method='post' action='/correos/prueba' style='display:flex;gap:10px;align-items:end;max-width:520px'><div style='flex:1'><label>Enviar prueba a</label><input type='email' name='destinatario' placeholder='tu_correo@gmail.com' required></div><button class='btn primary' type='submit'>Enviar prueba</button></form></div>
    <div class='card'><h3>Historial de correos</h3><table><thead><tr><th>Estado</th><th>Tipo</th><th>Destinatario</th><th>Asunto</th><th>Creado</th><th>Procesado</th><th>Mensaje/error</th></tr></thead><tbody>
    """
    for r in rows:
        body += f"<tr><td>{esc(r['status'])}</td><td>{esc(r['kind'])}</td><td>{esc(r['recipient'])}</td><td>{esc(r['subject'])}</td><td>{esc(r['created_at'])}</td><td>{esc(r.get('processed_at'))}</td><td>{esc(r.get('provider_response',''))[:180]}</td></tr>"
    body += "</tbody></table></div>"
    return layout("Correos", body, user)


@app.get("/correos/preparar")
def correos_preparar(request: Request):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user
    daily = monitor.queue_summary_emails()
    urgent = monitor.queue_urgent_emails()
    body = f"<div class='card'><h2>Correos preparados</h2><p>Resúmenes diarios nuevos: {daily}</p><p>Urgencias nuevas: {urgent}</p><a class='btn primary' href='/correos'>Volver</a></div>"
    return layout("Correos preparados", body, user)


@app.get("/correos/enviar")
def correos_enviar(request: Request):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user
    res = emailer.process_outbox()
    body = f"<div class='card'><h2>Correos procesados</h2><p>Procesados: {res['processed']}</p><p>Enviados: {res['sent']}</p><p>Errores: {res['errors']}</p><a class='btn primary' href='/correos'>Volver</a></div>"
    return layout("Correos procesados", body, user)


@app.get("/correos/limpiar-pruebas")
def correos_limpiar(request: Request):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user
    deleted = db.execute("DELETE FROM email_outbox WHERE status IN ('error','outbox') OR recipient ILIKE %s", ("%@ejemplo.com",))
    body = f"<div class='card'><h2>Limpieza realizada</h2><p>Eliminados: {deleted}</p><a class='btn primary' href='/correos'>Volver a correos</a></div>"
    return layout("Limpieza", body, user)


@app.post("/correos/prueba")
async def correos_prueba(request: Request):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user
    form = await request.form()
    dest = str(form.get("destinatario", "")).strip()
    subject = "Prueba CampoSeguro - correo de alertas"
    body_txt = "Hola,\n\nEste es un correo de prueba de CampoSeguro. Si recibes este mensaje, el envío por Resend está funcionando correctamente.\n\nCampoSeguro es una herramienta informativa."
    ok, provider, response = emailer.send_email(dest, subject, body_txt)
    if ok:
        body = f"<div class='card'><h2>Correo de prueba enviado</h2><p>Se envió un mensaje de prueba a:</p><b>{esc(dest)}</b><p>Proveedor: {esc(provider)}</p><a class='btn primary' href='/correos'>Volver a correos</a></div>"
    else:
        body = f"<div class='card'><h2>Error de correo</h2><p>No se pudo enviar a {esc(dest)}</p><pre>{esc(response)}</pre><a class='btn primary' href='/correos'>Volver</a></div>"
    return layout("Prueba correo", body, user)


@app.get("/base-de-datos")
def base_datos(request: Request):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user
    stats = counts_for()
    body = "<div class='card'><h2>Base de datos</h2><p>PostgreSQL en producción. No subas camposeguro.db a GitHub.</p></div>" + stats_grid(stats)
    return layout("Base de datos", body, user)


@app.get("/configuracion")
def configuracion(request: Request):
    user = require_admin(request)
    if isinstance(user, RedirectResponse): return user
    vals = {
        "APP_VERSION": config.APP_VERSION,
        "FIRMS_DAY_RANGE": config.FIRMS_DAY_RANGE,
        "FIRMS_AREA_BBOX": config.FIRMS_AREA_BBOX,
        "FIRMS_SOURCES": ", ".join(config.FIRMS_SOURCES),
        "DEFAULT_ZONE_RADIUS_KM": config.DEFAULT_ZONE_RADIUS_KM,
        "EMAIL_PROVIDER": config.EMAIL_PROVIDER,
        "EMAIL_DAILY_MAX_PER_RECIPIENT": config.EMAIL_DAILY_MAX_PER_RECIPIENT,
        "EMAIL_URGENT_COOLDOWN_HOURS": config.EMAIL_URGENT_COOLDOWN_HOURS,
        "MONITOR_INTERVAL_MINUTES": config.MONITOR_INTERVAL_MINUTES,
    }
    body = "<div class='card'><h2>Configuración operativa</h2><table><thead><tr><th>Variable</th><th>Valor actual</th></tr></thead><tbody>"
    for k, v in vals.items():
        body += f"<tr><td><b>{esc(k)}</b></td><td>{esc(v)}</td></tr>"
    body += "</tbody></table><div class='notice'>Las variables sensibles se cambian en Render → Environment.</div></div>"
    return layout("Configuración", body, user)
