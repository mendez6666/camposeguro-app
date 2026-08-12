# CampoSeguro v4.2.3 — Zonas sin duplicados + control de pagos

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
