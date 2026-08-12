# CampoSeguro v4.2.1 — Mapa regional y carga de zonas

Versión regional para Sudamérica con mejoras de visualización y registro de puntos de monitoreo.

## Cambios principales

- Filtro de mapa por país: Todos, Bolivia, Paraguay, Brasil, Perú, Argentina, Chile, Colombia, Ecuador, Uruguay, Venezuela, Guyana y Surinam.
- El mapa muestra “focos visualizados” para aclarar que se limita la cantidad de puntos dibujados y así evitar congelar el navegador.
- Los usuarios/clientes pueden agregar nuevas zonas desde su portal.
- Las zonas pueden cargarse de tres formas:
  - Latitud/longitud manual.
  - Enlace de Google Maps o texto con coordenadas.
  - Ubicación actual del dispositivo mediante GPS/navegador.
- El sistema mantiene la separación admin/cliente, alertas por radio y reportes.

## Recomendación operativa para clientes

Para registrar una finca, predio o comunidad:

1. Si está en el lugar y tiene internet, puede usar “Usar mi ubicación actual”.
2. Si está en el lugar pero no tiene internet, puede anotar las coordenadas con el GPS del celular y cargarlas luego.
3. Si no está en la finca, puede buscar el punto en Google Maps, copiar coordenadas o un enlace que contenga latitud/longitud y pegarlo en CampoSeguro.

## Variables recomendadas

FIRMS_AREA_BBOX=-82.0,-56.0,-34.0,13.0
OPERATING_REGION=Sudamérica
DEFAULT_COUNTRY=Bolivia
SUPPORTED_COUNTRIES=Bolivia,Paraguay,Brasil,Perú,Argentina,Chile,Colombia,Ecuador,Uruguay,Venezuela,Guyana,Surinam

## Subida recomendada

Para actualizar desde v4.2, sube principalmente:

- app.py
- config.py
- README.md

Si quieres hacer reemplazo completo, sube todos los archivos salvo `camposeguro.db` y `__pycache__`.
