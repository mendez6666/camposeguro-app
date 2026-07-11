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
FIRMS_QUERY_DAYS=5
ALERT_WINDOW_HOURS=24
FIRMS_SOURCES=MODIS_NRT,VIIRS_SNPP_NRT,VIIRS_NOAA20_NRT,VIIRS_NOAA21_NRT
EMAIL_ENABLED=false
```

## Prueba FIRMS

Después de desplegar, abre:

```text
/prueba-firms
```

Esa pantalla prueba FIRMS desde Render sin guardar datos.## Versión 1.9

Esta versión usa una estrategia automática FIRMS:

1. Consulta Santa Cruz.
2. Si no encuentra focos, consulta Bolivia.
3. No consulta toda Sudamérica para evitar ruido y exceso de datos.

La API regional sigue siendo `South_America`, pero el BBOX operativo es Santa Cruz/Bolivia.
## Versión 2.0

La alerta temprana se mantiene así:

- `FIRMS_QUERY_DAYS=5`: consulta técnica de respaldo para evitar que Render/API devuelva vacío por desfase o ventana corta.
- `ALERT_WINDOW_HOURS=24`: solo los focos de las últimas 24 horas generan alertas.
- Estrategia automática: Santa Cruz → Bolivia.
## Versión 2.1 Producción Demo

Cambios:
- Menú limpio para presentación.
- Se oculta la pestaña pública de prueba FIRMS.
- El mapa inicia con zonas + alertas, sin saturarse con todos los focos.
- Botones de capas: solo alertas, zonas, focos, todo y limpiar focos.
- Ruta técnica `/prueba-firms` se mantiene para diagnóstico, pero no aparece en el menú.
- Ruta `/landing` agregada como página simple de presentación.
## Versión 2.2 - Mapa con contexto de fuego

Cambio principal:
- El mapa abre con zonas + alertas + focos cercanos de contexto.
- Los focos cercanos se calculan alrededor de cada zona monitoreada usando radio de zona + 60 km.
- Esto permite ver de dónde puede venir la presión de fuego sin saturar con todos los focos de Santa Cruz.
- Los 5000 focos generales siguen disponibles con el botón "Todos los focos".
## Versión 2.3 - Mapa regional + operativo

Cambio principal:
- La vista inicial ahora muestra todos los focos regionales descargados junto con zonas y alertas.
- Los focos regionales se muestran con puntos pequeños y semitransparentes.
- Las alertas quedan encima con mayor tamaño y prioridad visual.
- Se agregan modos: Vista regional, Vista operativa, Solo alertas, Focos cercanos y Limpiar focos.
- Esto permite ver el panorama Santa Cruz/Bolivia y también analizar focos cercanos a zonas monitoreadas.
