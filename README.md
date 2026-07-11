# CampoSeguro

Plataforma de alerta temprana informativa de focos de calor para zonas registradas.

## Render

Build Command:

```bash
pip install -r requirements.txt
```

Start Command:

```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

## Variables de entorno en Render

```env
FIRMS_MAP_KEY=tu_llave_firms
FIRMS_AREA_BBOX=-64.9,-20.6,-57.0,-13.0
FIRMS_DAY_RANGE=1
FIRMS_SOURCES=MODIS_NRT,VIIRS_SNPP_NRT,VIIRS_NOAA20_NRT,VIIRS_NOAA21_NRT
EMAIL_ENABLED=false
```

## Prueba FIRMS

Después de desplegar, abre:

```text
/prueba-firms
```

Esa pantalla prueba FIRMS desde Render sin guardar datos.