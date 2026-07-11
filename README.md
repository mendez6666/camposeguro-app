# CampoSeguro

Plataforma de alerta temprana informativa de focos de calor para zonas registradas.

## Despliegue en Render

### Build Command

```bash
pip install -r requirements.txt
```

### Start Command

```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

## Variables de entorno necesarias en Render

```env
FIRMS_MAP_KEY=tu_llave_firms
FIRMS_AREA_BBOX=-64.9,-20.6,-57.0,-13.0
FIRMS_DAY_RANGE=1
FIRMS_SOURCES=MODIS_NRT,VIIRS_SNPP_NRT,VIIRS_NOAA20_NRT,VIIRS_NOAA21_NRT
EMAIL_ENABLED=false
```

## Variables de correo para envío real posterior

```env
EMAIL_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USER=tu_correo@gmail.com
SMTP_PASSWORD=tu_app_password
SMTP_FROM=CampoSeguro <tu_correo@gmail.com>
```

## Archivos que NO deben subirse

No subir:

```text
.env
camposeguro.db
output/
__pycache__/
```

## Nota

Esta versión usa SQLite local. Para demo en Render Free está bien. Para producción estable se recomienda migrar a PostgreSQL.