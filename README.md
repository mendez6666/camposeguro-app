# CampoSeguro v4.1 — Plataforma escalable

Versión preparada para pasar de prototipo a operación con múltiples clientes.

## Concepto operativo

- **Focos FIRMS**: puntos satelitales descargados para el área operativa.
- **Zona monitoreada**: punto o área de interés de un cliente con radio configurable.
- **Zona con alerta**: zona que tiene uno o más focos dentro de su radio.
- **Correo diario**: máximo un resumen diario por destinatario.
- **Urgencia**: solo para nivel crítico, con enfriamiento configurable para no saturar al cliente.

## Arquitectura recomendada

```text
NASA FIRMS
   ↓
Monitor automático / worker
   ↓
PostgreSQL
   ↓
Alertas agrupadas por zona y cliente
   ↓
Portal web + correos Resend
```

## Variables principales en Render

```env
DATABASE_URL=postgresql://...
SESSION_SECRET=un-secreto-largo
PUBLIC_BASE_URL=https://app.camposeguro.app

ADMIN_EMAIL=tu_correo@dominio.com
ADMIN_PASSWORD=Cambiar123!

FIRMS_MAP_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
FIRMS_AREA_BBOX=-70.0,-23.5,-57.0,-9.0
FIRMS_DAY_RANGE=5
FIRMS_SOURCES=MODIS_NRT,VIIRS_SNPP_NRT,VIIRS_NOAA20_NRT,VIIRS_NOAA21_NRT

EMAIL_ENABLED=true
EMAIL_PROVIDER=resend_api
RESEND_API_KEY=re_xxxxxxxxxxxxx
EMAIL_FROM=CampoSeguro <alertas@camposeguro.app>
EMAIL_REPLY_TO=tu_correo@dominio.com

MONITOR_INTERVAL_MINUTES=180
AUTO_MONITOR_ENABLED=true
EMAIL_DAILY_MAX_PER_RECIPIENT=1
EMAIL_URGENT_ENABLED=true
EMAIL_URGENT_COOLDOWN_HOURS=12
```

## Render

Web service:

```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

Worker recomendado cuando ya haya clientes pagos:

```bash
python auto_monitor.py
```

Cuando uses worker separado, deja en el web service:

```env
AUTO_MONITOR_ENABLED=false
```

y en el worker:

```env
AUTO_MONITOR_ENABLED=true
```

## Acceso

Al iniciar, el sistema crea:

- Un administrador con `ADMIN_EMAIL` y `ADMIN_PASSWORD`.
- Un cliente piloto con `CLIENT_DEMO_EMAIL` y `CLIENT_DEMO_PASSWORD`.

Cada cliente solo ve sus zonas, alertas y reporte.

## Notas importantes

- No subir `camposeguro.db` a GitHub.
- No crear una variable `CLIENT_USER_ID` por cliente.
- El radio se guarda por zona y recalcula alertas.
- Las alertas son agrupadas: una zona puede tener muchos focos, pero genera una sola alerta operativa.
- Los correos son anti-saturación: resumen diario y urgencias con enfriamiento.
