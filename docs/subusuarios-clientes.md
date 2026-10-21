# Subusuarios del cliente EXIT

Desde **Mi cuenta → Subusuarios**, la cuenta principal puede crear accesos por correo y nombre, habilitarlos o deshabilitarlos, renovar su clave inicial y generar o revocar su QR personal. Los subusuarios mantienen el cliente comercial EXIT de la cuenta principal; no se crean clientes maestros nuevos en EXIT.

Cada subusuario tiene cinco permisos independientes:

- Ver precios de venta.
- Ver albaranes del cliente EXIT.
- Ver facturas del cliente EXIT.
- Cambiar sus preferencias de visualización (miniaturas).
- Ver únicamente sus propios pedidos. Si se desmarca, ve los pedidos del mismo cliente EXIT.

Por defecto se ocultan los precios y documentos, se permiten las preferencias personales y se muestran solo los pedidos propios. Los parámetros generales de operación siguen siendo exclusivos del operador.

Los permisos se comprueban en el servidor. Sin permiso de precios, la API devuelve `null` en los importes y la web muestra `••••`. Las descargas PDF/Excel que contienen precios se bloquean. El pedido conserva sus importes reales para EXIT y la cuenta principal. El permiso de pedidos propios se aplica también al detalle, duplicación, envío de borradores y eliminación, y no atribuye al subusuario pedidos externos sin vínculo con un pedido suyo.

El pedido guarda `customer_code` (cliente EXIT), `principal_user_id`, `principal_user_name`, `user_id` (creador) y `creator_user_name`. Los nombres quedan como fotografía del momento de creación; los pedidos antiguos conservan sus datos históricos. La API de integración recibe estos datos al consultar el pedido.

La clave inicial se muestra a la cuenta principal hasta que el subusuario la cambie o caduque. Al renovarla se revocan sesiones y QR anteriores. Los cambios de permisos cierran las sesiones del subusuario. La deshabilitación del principal impide también el acceso de sus subusuarios. Los subusuarios entran por su propio código (por ejemplo `SU-00000042`), correo o QR. El código propio es visible en la lista, la ficha y Mi cuenta; el código EXIT identifica únicamente a la cuenta principal. El principal puede editar nombre, correo y teléfono del subusuario. Los datos fiscales y comerciales siguen siendo los del cliente EXIT compartido. Al actualizar el correo, el código y QR siguen identificando al mismo usuario.

## Instalación

Requiere actualizar conjuntamente API y frontend. El arranque habitual de la API ejecuta `python -m app.bootstrap`, que añade de forma idempotente las columnas e índices de usuarios y pedidos en PostgreSQL, incluido un código único para los subusuarios que ya existan. No modifica maestros de EXIT ni crea subusuarios reales automáticamente. Las cuentas actuales mantienen sus permisos anteriores.

Validar primero en desarrollo: crear una subcuenta, entrar con su clave inicial, cambiarla, realizar un pedido y revisar las dos identidades con el principal. Comprobar los cinco permisos y la entrada con QR antes de pasar a producción.
