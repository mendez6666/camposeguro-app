# CampoSeguro v4.0 — Portal seguro para múltiples clientes

Versión para piloto comercial seguro.

## Qué cambia

- Cada usuario registrado tiene un **enlace privado de cliente**.
- Ya no hace falta cambiar `CLIENT_USER_ID` en Render para probar diferentes clientes.
- El cliente entra por su enlace y solo ve sus zonas, sus alertas, su mapa y su reporte.
- El cliente **no puede ejecutar monitoreo**, no puede ver usuarios, base de datos, configuración ni correos.
- El administrador mantiene el monitoreo automático y el envío de correos controlados.
- Se mantiene la lógica anti-saturación de v3.9: resumen diario y urgencias críticas controladas.

## Uso recomendado

1. Sube todos los archivos de esta carpeta a GitHub.
2. Espera que Render despliegue correctamente.
3. Entra como administrador.
4. Ve a **Usuarios**.
5. Copia el **Enlace cliente** de cada usuario.
6. Comparte ese enlace solo con el cliente correspondiente.

## Variables recomendadas en Render

```env
AUTH_ENABLED=true
ADMIN_USER=admin
ADMIN_PASSWORD=TU_PASSWORD_ADMIN
SESSION_SECRET=UN_TEXTO_LARGO_SECRETO
AUTH_COOKIE_SECURE=true

CLIENT_PORTAL_ENABLED=true
APP_PUBLIC_URL=https://app.camposeguro.app

AUTO_MONITOR_ENABLED=true
AUTO_MONITOR_INTERVAL_MINUTES=180
AUTO_MONITOR_RUN_ON_STARTUP=true

EMAIL_ENABLED=true
EMAIL_PROVIDER=resend_api
RESEND_API_KEY=TU_API_KEY_DE_RESEND
SMTP_FROM=CampoSeguro <alertas@camposeguro.app>
EMAIL_REPLY_TO=tu_correo@dominio.com
EMAIL_MODE=daily_plus_critical
EMAIL_DAILY_MAX_PER_RECIPIENT=1
EMAIL_URGENT_MIN_LEVEL=CRITICO
EMAIL_URGENT_COOLDOWN_HOURS=24
EMAIL_TIMEZONE_OFFSET_HOURS=-4
EMAIL_MIN_LEVEL=ATENCION
EMAIL_MAX_PER_ZONE=3
EMAIL_SUMMARY_MAX_ALERTS=10
```

## Importante

No compartas la clave de administrador. Para clientes usa únicamente los enlaces privados generados en la sección **Usuarios**.
