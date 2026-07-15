# CampoSeguro v3.9 — Resumen diario y urgencias controladas

Versión comercial anti-saturación.

## Qué cambia

- El monitoreo puede correr cada 3 horas, pero el cliente no recibe muchos correos.
- CampoSeguro envía máximo 1 resumen diario por destinatario.
- Si aparece una alerta CRÍTICA, puede enviar una urgencia, pero con enfriamiento configurable.
- La lógica respeta el radio actual de cada zona: si el cliente cambia de 15 km a 5 km, las alertas y correos se recalculan con ese nuevo radio.
- El correo muestra el radio configurado por zona, distancia mínima y foco priorizado.
- Corrige error visual de CSS `.compact-list` que podía causar error interno.

## Variables recomendadas en Render

```env
EMAIL_ENABLED=true
EMAIL_PROVIDER=resend_api
RESEND_API_KEY=TU_API_KEY_DE_RESEND
SMTP_FROM=CampoSeguro <alertas@camposeguro.app>
EMAIL_REPLY_TO=mmendez@sbda.org.bo
APP_PUBLIC_URL=https://app.camposeguro.app

EMAIL_MODE=daily_plus_critical
EMAIL_DAILY_MAX_PER_RECIPIENT=1
EMAIL_URGENT_MIN_LEVEL=CRITICO
EMAIL_URGENT_COOLDOWN_HOURS=24
EMAIL_TIMEZONE_OFFSET_HOURS=-4
EMAIL_MIN_LEVEL=ATENCION
EMAIL_MAX_PER_ZONE=3
EMAIL_SUMMARY_MAX_ALERTS=10
```

## Uso operativo

1. El admin mantiene el monitoreo cada 180 minutos.
2. El cliente ajusta radios en Mis zonas.
3. CampoSeguro recalcula alertas con el radio vigente.
4. El correo diario resume zonas con alerta.
5. La urgencia solo sale para CRÍTICO y no se repite durante el cooldown.
