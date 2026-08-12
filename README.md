# CampoSeguro v4.2 — Regionalización Sudamérica

Primera parte del paso comercial regional.

## Qué cambia

- Actualiza la versión a 4.2.
- Cambia el enfoque textual de Bolivia a Sudamérica.
- Cambia el BBOX FIRMS por defecto a Sudamérica continental: `-82.0,-56.0,-34.0,13.0`.
- Agrega país a usuarios/clientes.
- Agrega país a zonas monitoreadas.
- Muestra país en usuarios, zonas, alertas, reportes y CSV.
- Mantiene el portal cliente, radios, alertas, reportes y correos.

## Qué subir a GitHub

Subir estos archivos:

- `app.py`
- `db.py`
- `config.py`
- `README.md`
- `.env.example`

No tocar variables de Render salvo que quieras fijar explícitamente:

```env
OPERATING_REGION=Sudamérica
DEFAULT_COUNTRY=Bolivia
SUPPORTED_COUNTRIES=Bolivia,Paraguay,Brasil,Perú,Argentina,Chile,Colombia,Ecuador,Uruguay,Venezuela,Guyana,Surinam
FIRMS_AREA_BBOX=-82.0,-56.0,-34.0,13.0
```

## Prueba después del deploy

1. `/healthz`
2. `/`
3. `/usuarios`
4. `/zonas`
5. `/mapa`
6. `/cliente`

## Nota

Esta versión NO integra pagos todavía. El siguiente paso será v4.3 con checkout web de Lemon Squeezy.
