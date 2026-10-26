# Accesos de operadores desde EXIT

En el menú de operador, **Accesos de usuarios** consulta `dbo.MCusuarios` con búsqueda y páginas de 25. Selecciona un usuario, una sede de EXIT y sus opciones permitidas. Guarda para generar su contraseña inicial. Puede habilitarse o deshabilitarse, generar otra clave o asignar una desde la web. Las contraseñas son independientes de EXIT, se guardan con Argon2 y nunca se incluyen en auditorías ni se consultan las claves de MCusuarios.

La tabla nueva PostgreSQL `operator_access` vincula `users.id` con el código de MCusuarios y guarda los permisos por módulo. La crea `app.bootstrap`. Los permisos se verifican en el servidor en cada petición y se usan también para ocultar opciones. Deshabilitar, cambiar permisos o restablecer contraseña revoca las sesiones. Un gestor no puede deshabilitarse a sí mismo ni quitarse la gestión de usuarios. Los administradores conservan el acceso. Las cuentas antiguas siguen siendo compatibles mientras se trasladan; solo los usuarios habilitados expresamente desde MCusuarios reciben permisos por módulo.

## Campos de MCusuarios

Se utiliza la consulta facilitada, con búsqueda y paginación parametrizadas:

```sql
SELECT m.CodigoUsuario, m.NombreCorto, m.Correo
FROM MCUsuarios m
```

`CodigoUsuario` es la clave de vinculación con PostgreSQL. `NombreCorto` es el nombre visible y el usuario de entrada. `Correo`, si está informado, es también un identificador para iniciar sesión; sin correo se conserva el nombre corto. Si el nombre corto está vacío se utiliza el código. El código numérico cero se conserva. No se consultan metadatos ni se buscan campos alternativos. Los usuarios pueden entrar por código, nombre corto o correo, con una sola contraseña web.

La pantalla muestra el correo y permite buscarlo. Al guardar una cuenta existente se actualizan nombre corto y correo desde EXIT, conservando contraseña e historial; se rechazan colisiones con identificadores de otras cuentas. Si falla solo la consulta de sedes, se conserva la lista de usuarios visible y se avisa; la asignación queda deshabilitada hasta recuperar las sedes. Los errores de MCUsuarios, accesos locales y sedes se distinguen en la respuesta y en el registro. La consulta real desde este entorno local sigue sin poder ejecutarse por falta de configuración SQL Server.

## Traslado inicial a RPA

En PostgreSQL, el arranque busca un único RPA real en MCusuarios. Reutiliza la cuenta `operador@bermudez.test` si existe, manteniendo su identificador y trazabilidad; reemplaza su acceso por `RPA`, asigna todos los módulos y cierra las sesiones antiguas. Conserva la sede anterior si sigue existiendo; de lo contrario utiliza la primera sede devuelta por EXIT (revisarla en la interfaz). La contraseña inicial solicitada se prepara una sola vez. Deberá cambiarse al entrar, como los demás accesos iniciales.

Si la conexión o la consulta de los campos indicados falla, el traslado no se realiza, queda una advertencia en el registro y se conserva el operador anterior para no bloquear el acceso. Tras corregirlo, se puede reintentar desde el directorio backend con `PYTHONPATH=. python scripts/provision_rpa.py`. El proceso nunca restablece contraseñas, permisos ni accesos deshabilitados de un RPA ya vinculado. No modifica MCusuarios. No cambia las credenciales de integración del robot (`integration_api_key`).

## Validación

Pruebas con EXIT simulado: paginación, usuarios no existentes, sede inválida, colisiones, permisos comprobados por API, cambio obligatorio de clave, revocación de sesiones, impedir autobloqueo, traslado conservando identidad e idempotencia de RPA y consulta SQL parametrizada sin campos de contraseña. La comprobación con SQL Server real y el despliegue están pendientes.
