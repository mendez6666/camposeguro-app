# CampoSeguro v4.2.4 — Prueba gratis 5 días + suspensión automática

Versión comercial regional para Sudamérica.

## Cambios principales

- Mantiene la mejora de v4.2.2: evita duplicados al crear zonas.
- Agrega botón para eliminar zonas y limpieza de duplicadas.
- Agrega registro de zonas por GPS, coordenadas, Google Maps o clic en mapa.
- Agrega control comercial de suscripción por cliente.
- No elimina automáticamente zonas cuando un cliente no paga.
- Si vence el pago mensual, el cliente queda suspendido y sus zonas quedan guardadas.
- Clientes suspendidos no ven mapa, zonas, alertas ni reporte hasta reactivación.
- Admin puede suspender o reactivar clientes por 30 días.
- El monitor y los correos ignoran clientes suspendidos.

## Regla comercial recomendada

No borrar zonas por falta de pago. Suspender el acceso y reactivar cuando pague.

## Subir a GitHub

Subir principalmente:

- app.py
- config.py
- db.py
- monitor.py
- README.md
- LEEME_PRIMERO.txt

No subir:

- camposeguro.db
- __pycache__


## v4.2.4 — prueba gratis 5 días + suspensión automática
- Cliente nuevo puede iniciar con prueba gratuita de 5 días.
- Si la prueba vence y no hay pago, el cliente pasa a SUSPENDIDO automáticamente.
- Si el pago mensual vence, también se suspende automáticamente.
- No se eliminan zonas ni radios: quedan guardados para reactivación.
- El admin tiene botones: Prueba 5 días, Suspender y Reactivar 30 días.
- El monitor y los correos ignoran clientes suspendidos o vencidos.
- Esta versión prepara la integración futura con pasarela de pago por tarjeta.
