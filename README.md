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
## Versión 2.4 - Bolivia activa

Cambio principal:
- CampoSeguro consulta Bolivia completa como área operativa principal.
- La API regional sigue siendo South_America, pero el BBOX operativo es Bolivia:
  -70.0,-23.5,-57.0,-9.0
- Esto permite incluir Santa Cruz, Beni, Pando y otros departamentos.
- Las alertas tempranas siguen filtradas a las últimas 24 horas mediante ALERT_WINDOW_HOURS=24.
- La consulta técnica puede seguir usando FIRMS_QUERY_DAYS=5 para evitar vacíos por desfase temporal/API.
## Versión 2.5 - Login y protección básica

Cambio principal:
- La plataforma queda protegida con inicio de sesión.
- Rutas públicas: `/login`, `/logout`, `/landing`, `/healthz`.
- El resto de la plataforma queda detrás del login.
- Se recomienda configurar estas variables en Render antes de desplegar:

```env
AUTH_ENABLED=true
ADMIN_USER=admin
ADMIN_PASSWORD=elige_una_contrasena_segura
SESSION_SECRET=elige_un_texto_largo_aleatorio
AUTH_COOKIE_SECURE=true
AUTH_SESSION_HOURS=12
```

Importante:
- No subas la contraseña real a GitHub.
- La contraseña debe configurarse en Render → Environment.
## Versión 2.7 - Alertas por período y mapa corregido

Cambios principales:
- Las alertas se recalculan con `ALERT_EVALUATION_HOURS`, por defecto 120 horas.
- Esto evita que focos descargados dentro de una zona queden sin alerta solo por estar fuera de 24h.
- El mapa separa correctamente:
  - Vista operativa: zonas + alertas + focos cercanos.
  - Bolivia completa: todos los focos descargados + zonas + alertas.
  - Zonas + focos: zonas + focos cercanos.
  - Alertas + focos: alertas + zonas + focos cercanos.
  - Todo: todas las capas.
- Mantiene login básico de v2.5.
## Versión 2.8 - Mapa simple y profesional

Cambio principal:
- Se simplifica el mapa para que sea más intuitivo.
- Se eliminan los puntos azules de alertas del mapa.
- El mapa queda con tres botones:
  - Zonas
  - Focos
  - Todo
- Las alertas quedan en las pestañas Alertas y Reporte, no mezcladas como puntos en el mapa.
- Las zonas se muestran como círculos azules con centro pequeño.
- Los focos se muestran como puntos FIRMS MODIS/VIIRS.
## Versión 2.9 - Modo administrador y modo cliente

Cambio principal:
- Se agregan dos tipos de acceso:
  - Administrador: panel completo.
  - Cliente: vista simple y solo lectura.

Variables nuevas recomendadas en Render:
```env
CLIENT_USER=cliente
CLIENT_PASSWORD=elige_una_contrasena_cliente
CLIENT_NAME=Cliente CampoSeguro
```

Rutas cliente:
- `/cliente`
- `/cliente/mapa`
- `/cliente/alertas`
- `/cliente/reporte`

El cliente no puede acceder a:
- Usuarios
- Zonas de edición
- Configuración
- Correos
- Actualizar monitoreo
- Prueba FIRMS
## Versión 3.0 - Radios configurables y correos controlados

Cambios principales:
- Se agrega `/cliente/zonas` para que el cliente ajuste el radio de sus zonas sin tocar coordenadas.
- El radio recomendado baja a 15 km.
- El administrador puede aplicar el radio recomendado a todas las zonas desde Zonas.
- Los correos se controlan para evitar saturación:
  - `EMAIL_MIN_LEVEL=ATENCION`
  - `EMAIL_MAX_PER_ZONE=1`
- Esto evita enviar cientos de correos por focos informativos o muy lejanos.

Variables nuevas recomendadas en Render:
```env
DEFAULT_ZONE_RADIUS_KM=15
CLIENT_MIN_RADIUS_KM=1
CLIENT_MAX_RADIUS_KM=50
EMAIL_MIN_LEVEL=ATENCION
EMAIL_MAX_PER_ZONE=1
```

Nota sobre correos:
- `EMAIL_ENABLED=false` no envía correos reales. Solo prepara/genera outbox.
- Para correo real faltan variables SMTP: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM.
