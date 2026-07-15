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
## Versión 3.1 - Monitoreo automático

Cambios principales:
- Se agrega monitor automático interno.
- Se agrega panel administrativo `/monitor`.
- Se agrega endpoint protegido para cron externo: `/cron/monitor?token=TU_TOKEN`.
- El monitor ejecuta:
  1. Consulta FIRMS.
  2. Guarda focos nuevos.
  3. Recalcula alertas.
  4. Prepara correos.
  5. Procesa correos: envía si SMTP está activo o genera outbox si SMTP no está activo.

Variables nuevas recomendadas en Render:
```env
AUTO_MONITOR_ENABLED=true
AUTO_MONITOR_INTERVAL_MINUTES=180
AUTO_MONITOR_RUN_ON_STARTUP=true
AUTO_MONITOR_START_DELAY_SECONDS=45
MONITOR_SECRET=elige_un_token_largo_para_cron
```

Nota importante para Render Free:
- El monitor interno funciona mientras el servicio está despierto.
- Si Render duerme el servicio por inactividad, el monitor se pausa.
- Para monitoreo 24/7 económico, usar después un cron externo gratuito que visite:
  `https://app.camposeguro.app/cron/monitor?token=TU_TOKEN`


## Versión 3.2 - Base de datos persistente PostgreSQL

Cambio principal:
- CampoSeguro ahora puede usar PostgreSQL externo mediante `DATABASE_URL`.
- Si `DATABASE_URL` está vacío, sigue funcionando con SQLite local para pruebas.
- Si `DATABASE_URL` está configurado, guarda datos en PostgreSQL persistente.

Qué se guarda en PostgreSQL:
- Usuarios
- Zonas
- Radios configurados
- Focos FIRMS guardados
- Alertas recalculadas
- Correos preparados/enviados/outbox

Variable nueva en Render:
```env
DATABASE_URL=pega_aqui_la_url_de_neon_o_supabase
```

Recomendación:
- Para piloto barato usar Neon PostgreSQL Free.
- Después de agregar `DATABASE_URL`, ejecutar: Manual Deploy → Clear build cache & deploy.
- Luego entrar a `/base-datos` para verificar que el motor diga `postgresql`.

Nota:
- La primera vez con PostgreSQL se crearán tablas nuevas y se cargarán zonas demo si la base está vacía.
- Si ya tenías datos en SQLite local, no se migran automáticamente a PostgreSQL. Para el piloto actual se puede recrear usuarios/zonas desde la app.


## Versión 3.3 - Correos reales con Resend SMTP

Esta versión agrega soporte para envío real de correos de alerta usando SMTP SSL, recomendado para Resend.

Variables para Render cuando Resend ya verificó el dominio:

```env
EMAIL_ENABLED=true
EMAIL_PROVIDER=resend
SMTP_HOST=smtp.resend.com
SMTP_PORT=465
SMTP_USE_SSL=true
SMTP_USE_TLS=false
SMTP_USER=resend
SMTP_PASSWORD=TU_API_KEY_DE_RESEND
SMTP_FROM=CampoSeguro <alertas@camposeguro.app>
EMAIL_REPLY_TO=tu_correo_de_respuesta@gmail.com
```

Recomendación:
- Mantener `EMAIL_ENABLED=false` hasta que Resend verifique `camposeguro.app`.
- Después activar `EMAIL_ENABLED=true`.
- Probar desde `/correos` usando el formulario "Prueba de correo SMTP".
- Mantener `EMAIL_MIN_LEVEL=ATENCION` y `EMAIL_MAX_PER_ZONE=1` para evitar saturación.

Importante:
- No usar Titan si solo se necesita enviar alertas transaccionales.
- No compartir `SMTP_PASSWORD` ni API keys en capturas.
- Si Resend aún no verifica el dominio, el envío puede fallar aunque las variables estén bien.


## v3.3.1 hotfix de arranque seguro

Esta versión corrige el despliegue en Render cuando la app queda en `Exited with status 1` sin mostrar error claro.

Cambios:
- PostgreSQL conecta con `connect_timeout=10`.
- El arranque ya no tumba todo el servicio por un error transitorio de base o monitor.
- Nueva ruta admin: `/diagnostico-arranque`.
- Mantiene soporte Resend SMTP de v3.3.

Recomendación de despliegue:
1. Subir todos los archivos a GitHub.
2. En Render mantener temporalmente `EMAIL_ENABLED=false`.
3. Hacer `Manual Deploy -> Clear build cache & deploy`.
4. Entrar a `/diagnostico-arranque`.
5. Si todo está bien, activar `EMAIL_ENABLED=true` y probar `/correos`.

## Versión 3.4 - Correos seguros y limpieza de pruebas

Corrige el problema de timeouts al procesar correos pendientes y evita enviar a direcciones de prueba como `correo@ejemplo.com`.

Incluye:
- Botón `Limpiar pruebas/errores` en `/correos`.
- Bloqueo automático de correos `@ejemplo.com` y `@example.com`.
- Procesamiento seguro por lotes pequeños: `EMAIL_PROCESS_LIMIT=3`.
- Timeout configurable: `EMAIL_SEND_TIMEOUT_SECONDS=20`.
- Mantiene Resend SMTP con `alertas@camposeguro.app`.

Después de desplegar:
1. Entrar a `/correos`.
2. Presionar `Limpiar pruebas/errores`.
3. Verificar usuarios reales en `/usuarios`.
4. Presionar `Preparar correos`.
5. Presionar `Procesar pendientes seguros`.


## Versión 3.5 - Resend API estable

Esta versión cambia el envío recomendado de SMTP a Resend API HTTPS para evitar cuelgues o timeouts al procesar correos pendientes en Render/Cloudflare.

Variables recomendadas en Render:

EMAIL_ENABLED=true
EMAIL_PROVIDER=resend_api
RESEND_API_KEY=tu_api_key_completa_de_resend
SMTP_FROM=CampoSeguro <alertas@camposeguro.app>
EMAIL_REPLY_TO=mmendez@sbda.org.bo
EMAIL_API_TIMEOUT_SECONDS=18

Las variables SMTP pueden quedar como respaldo, pero el envío principal usa la API HTTPS de Resend.


## CampoSeguro v3.5.1 - Hotfix config Resend API

Corrige el error de Render:
ImportError: cannot import name 'RESEND_API_KEY' from 'config'

Variables recomendadas en Render:
EMAIL_ENABLED=true
EMAIL_PROVIDER=resend_api
RESEND_API_KEY=re_...tu_api_key_completa_de_resend...
SMTP_FROM=CampoSeguro <alertas@camposeguro.app>
EMAIL_REPLY_TO=mmendez@sbda.org.bo
EMAIL_API_TIMEOUT_SECONDS=18

Luego usar:
Manual Deploy -> Clear build cache & deploy


## CampoSeguro v3.5.2 - Hotfix limpiar correos

Corrige la ruta /correos/limpiar-pruebas para que funcione también por GET.
Esto evita el error {"detail":"Not Found"} cuando se abre directamente la ruta o el botón actúa como enlace.

Después de subir a GitHub:
1. Verificar en app.py que exista: /correos/limpiar-pruebas
2. Render -> Manual Deploy -> Clear build cache & deploy
3. Entrar a /correos
4. Presionar Limpiar pruebas/errores
5. Enviar prueba a un correo real


## CampoSeguro v3.6 - Resumen inteligente de alertas

Mejoras principales:
- Envío de un solo correo resumen por destinatario.
- Agrupación de alertas por zona.
- Correo HTML profesional con métricas, zonas y botones a Google Maps.
- Respaldo en texto plano para compatibilidad.
- Límite diario por destinatario: EMAIL_DAILY_MAX_PER_RECIPIENT.
- Máximo de alertas visibles por resumen: EMAIL_SUMMARY_MAX_ALERTS.
- Mantiene protección anti-saturación y bloqueo de correos de ejemplo.

Variables nuevas recomendadas en Render:
APP_PUBLIC_URL=https://app.camposeguro.app
EMAIL_PROVIDER=resend_api
EMAIL_SUMMARY_MAX_ALERTS=20
EMAIL_DAILY_MAX_PER_RECIPIENT=4

Para instalar: subir app.py, emailer.py, config.py, requirements.txt y hacer Clear build cache & deploy en Render.


## CampoSeguro v3.6.2 - Fix definitivo logo y zoom

Cambios:
- Agrega LOGO_CAMPOSEGURO_URL = https://i.ibb.co/VWnQ8RZY/logo-campo-seguro.png
- Muestra logo en login, panel administrador y vista cliente.
- Mueve el zoom (+ / -) de Leaflet a abajo a la derecha con zoomControl:false.
- Incluye marcador de verificación: CAMPOSEGURO_LOGO_ZOOM_FIX_362.

Para verificar en GitHub:
1. Abrir app.py
2. Buscar: CAMPOSEGURO_LOGO_ZOOM_FIX_362
3. Buscar: LOGO_CAMPOSEGURO_URL
4. Buscar: bottomright

Para desplegar:
Render -> Manual Deploy -> Clear build cache & deploy.


## CampoSeguro v3.6.3 - Corrección definitiva NameError logo

Corrige el error de Render:
NameError: name 'LOGO_CAMPOSEGURO_URL' is not defined.

Cambios:
- El HTML usa directamente el URL del logo: https://i.ibb.co/VWnQ8RZY/logo-campo-seguro.png
- Se mantiene el zoom del mapa abajo a la derecha.
- Marcador de verificación en app.py: CAMPOSEGURO_LOGO_RUNTIME_FIX_363

Subir mínimo:
- app.py

Luego:
Render -> Manual Deploy -> Clear build cache & deploy


## CampoSeguro v3.6.4 - Logo compacto profesional

Cambios:
- El logo ya no ocupa una cabecera gigante.
- El logo queda pequeño, alineado a la izquierda.
- La cabecera vuelve a ser compacta y profesional.
- El control + / - del mapa queda abajo a la derecha.
- Marcador de verificación en app.py: CAMPOSEGURO_LOGO_COMPACTO_PRO_364

Subir mínimo:
- app.py

Luego:
Render -> Manual Deploy -> Clear build cache & deploy.


## CampoSeguro v3.7 - Piloto cliente real

Cambios principales:
- Vista cliente filtrable por usuario real usando `CLIENT_USER_ID`.
- Alternativa de filtrado por correo usando `CLIENT_EMAIL`.
- El cliente ve solo sus zonas, sus alertas y su reporte.
- El mapa cliente muestra solo zonas asignadas al cliente y focos FIRMS como contexto regional.
- El cliente puede ajustar radios por zona dentro del rango permitido.
- Reporte CSV descargable en `/cliente/reporte.csv`.
- La página `/usuarios` muestra el ID de cada usuario para configurar el piloto en Render.

Variables nuevas recomendadas en Render:
- `CLIENT_USER_ID=ID_DEL_USUARIO`
- `CLIENT_EMAIL=` solo si prefieres filtrar por correo
- `CLIENT_MIN_RADIUS_KM=1`
- `CLIENT_MAX_RADIUS_KM=50`

Flujo recomendado:
1. Entrar como admin.
2. Ir a Usuarios y crear/editar el cliente real.
3. Copiar su ID usuario.
4. Ir a Render > Environment y poner `CLIENT_USER_ID` con ese número.
5. Hacer Manual Deploy.
6. Entrar con usuario cliente y revisar `/cliente`, `/cliente/mapa`, `/cliente/zonas`, `/cliente/alertas`.
