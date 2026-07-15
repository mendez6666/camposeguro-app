# CampoSeguro v3.8 — Alertas agrupadas profesionales

Versión orientada a que el cliente entienda correctamente la diferencia entre **focos FIRMS de contexto** y **alertas operativas por zona**.

## Concepto operativo

- **Focos FIRMS**: todos los puntos satelitales descargados para el área operativa.
- **Zona con alerta**: una zona monitoreada que tiene uno o más focos dentro del radio configurado.
- **Focos asociados**: focos FIRMS que entran dentro del radio de una zona.

Esto evita saturar al cliente con una alerta por cada punto y permite enviar una lectura ejecutiva: una zona con riesgo puede agrupar varios focos.

## Cambios v3.8

- Panel de alertas agrupado por zona.
- Resumen ejecutivo con “Zonas con alerta” y “Focos asociados”.
- Reporte operativo agrupado por zona.
- Vista cliente con tarjetas de alerta agrupadas.
- Mapa con focos asociados resaltados en amarillo con borde oscuro.
- Mantiene la actualización en segundo plano para evitar timeout 524.

## Archivos recomendados para actualizar

Subir a GitHub:

- `app.py`
- `README.md`

Opcionalmente subir todos los archivos si se quiere mantener la carpeta completa sincronizada.

## Después de desplegar

En Render:

1. Manual Deploy
2. Clear build cache & deploy
3. Abrir `https://app.camposeguro.app/monitor`
4. Esperar que “Ejecutándose ahora” sea “No”
5. Revisar:
   - `/mapa`
   - `/alertas`
   - `/resumen`
   - `/reporte`
   - `/cliente`

