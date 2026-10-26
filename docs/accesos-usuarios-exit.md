# Accesos de operadores desde EXIT

En el menú de operador, **Accesos de usuarios** consulta `dbo.MCusuarios` con búsqueda y páginas de 25. Selecciona un usuario, una sede de EXIT y sus opciones permitidas. Guarda para generar su contraseña inicial. Puede habilitarse o deshabilitarse, generar otra clave o asignar una desde la web. Las contraseñas son independientes de EXIT, se guardan con Argon2 y nunca se incluyen en auditorías ni se consultan las claves de MCusuarios.

La tabla nueva PostgreSQL `operator_access` vincula `users.id` con el código de MCusuarios y guarda los permisos por módulo. La crea `app.bootstrap`. Los permisos se verifican en el servidor en cada petición y se usan también para ocultar opciones. Deshabilitar, cambiar permisos o restablecer contraseña revoca las sesiones. Un gestor no puede deshabilitarse a sí mismo ni quitarse la gestión de usuarios. Los administradores conservan el acceso. Las cuentas antiguas siguen siendo compatibles mientras se trasladan; solo los usuarios habilitados expresamente desde MCusuarios reciben permisos por módulo.

## Campos de MCusuarios

No se ha podido comprobar la tabla real desde el entorno local. `app/exit_users.py` consulta `INFORMATION_SCHEMA.COLUMNS`, resuelve código (`CodigoUsuario`, `IdUsuario`, `Usuario`), usuario de entrada (`Usuario`, `Login`, `NombreUsuario`, `CodigoUsuario`) y nombre (`Nombre`, `NombreCompleto`, `NombreUsuario`, `Descripcion`, `Usuario`). Selecciona únicamente estos campos. Si no se identifican, devuelve un error explícito sin crear usuarios. Confirmar este mapa en desarrollo; ajustar los candidatos a las columnas reales si fuera necesario. Los códigos deben ser únicos; se rechazan colisiones de acceso con otras cuentas.

## Traslado inicial a RPA

En PostgreSQL, el arranque busca un único RPA real en MCusuarios. Reutiliza la cuenta `operador@bermudez.test` si existe, manteniendo su identificador y trazabilidad; reemplaza su acceso por `RPA`, asigna todos los módulos y cierra las sesiones antiguas. Conserva la sede anterior si sigue existiendo; de lo contrario utiliza la primera sede devuelta por EXIT (revisarla en la interfaz). La contraseña inicial solicitada se prepara una sola vez. Deberá cambiarse al entrar, como los demás accesos iniciales.

Si la conexión o el mapa de campos falla, el traslado no se realiza, queda una advertencia en el registro y se conserva el operador anterior para no bloquear el acceso. Tras corregirlo, se puede reintentar desde el directorio backend con `PYTHONPATH=. python scripts/provision_rpa.py`. El proceso nunca restablece contraseñas, permisos ni accesos deshabilitados de un RPA ya vinculado. No modifica MCusuarios. No cambia las credenciales de integración del robot (`integration_api_key`).

## Validación

Pruebas con EXIT simulado: paginación, usuarios no existentes, sede inválida, colisiones, permisos comprobados por API, cambio obligatorio de clave, revocación de sesiones, impedir autobloqueo, traslado conservando identidad e idempotencia de RPA y consulta SQL parametrizada sin campos de contraseña. La comprobación con SQL Server real y el despliegue están pendientes.
