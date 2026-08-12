# CampoSeguro v4.2.5 — Landing pública + registro de prueba gratuita

Versión preparada para convertir CampoSeguro en un producto vendible, no solo en panel privado.

## Cambios principales

- `/` ahora es una landing pública si el visitante no inició sesión.
- `/planes` muestra planes piloto y beneficios.
- `/registro` permite crear cuenta de prueba gratuita de 5 días.
- El registro crea usuario cliente en estado `trial`.
- El cliente entra automáticamente a `/cliente` después de registrarse.
- La prueba gratuita conserva el límite configurado de zonas (`TRIAL_MAX_ZONES`).
- Si la prueba o el pago vencen, el sistema suspende automáticamente sin borrar zonas.
- `/login` conserva acceso privado para clientes y administrador.
- Admin autenticado sigue viendo el dashboard interno en `/`.

## Flujo comercial

1. Visitante entra a `https://app.camposeguro.app`.
2. Ve qué es CampoSeguro, planes y beneficios.
3. Hace clic en `Probar gratis 5 días`.
4. Crea cuenta con país, correo, teléfono y contraseña.
5. Entra al portal cliente.
6. Registra finca/zona con GPS, Google Maps, coordenadas o clic en mapa.
7. Si no paga al vencer la prueba, queda suspendido; sus zonas quedan guardadas.
8. Si paga, se reactiva por 30 días o según la pasarela de pago cuando se integre.

## Rutas públicas

- `/` landing pública
- `/planes` planes y precios piloto
- `/registro` registro de prueba gratuita
- `/login` acceso para clientes existentes

## Rutas privadas admin

- `/usuarios`
- `/zonas`
- `/monitor`
- `/correos`
- `/configuracion`

## Rutas privadas cliente

- `/cliente`
- `/cliente/mapa`
- `/cliente/zonas`
- `/cliente/zonas/nueva`
- `/cliente/alertas`
- `/cliente/reporte`

## No subir a GitHub

- `camposeguro.db`
- `__pycache__`
- archivos `.pyc`
