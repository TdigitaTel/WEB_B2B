# Consultar la clave inicial de un cliente

En Operaciones → Accesos de clientes, busca el código EXIT exacto y pulsa Seleccionar. Si el cliente está activo, pendiente de cambiar su contraseña y la clave inicial no ha caducado, se muestran el usuario y la clave inicial. Nunca se muestra su contraseña personal.

Las claves iniciales nuevas se guardan con cifrado autenticado Fernet en users.initial_password_ciphertext; password_hash sigue siendo el hash Argon2 usado para autenticar. La clave de cifrado se deriva del JWT_SECRET existente con una etiqueta exclusiva para este uso. Si cambia JWT_SECRET, las claves iniciales antiguas no podrán recuperarse y deben regenerarse.

Al cambiar la contraseña o deshabilitar el acceso se borra el valor cifrado. Una clave caducada no se muestra y su copia cifrada se borra al intentar consultarla. Ver o regenerar claves requiere rol de operador o administrador y queda auditado sin registrar la contraseña.

Las cuentas antiguas solo tienen hash: pulsa Generar nueva clave inicial para sustituir una clave pendiente que no se pueda recuperar. La anterior deja de servir y las sesiones se revocan. No se puede usar esta opción después de que el cliente haya cambiado a su contraseña personal.

El inicio de sesión acepta el usuario mostrado (correo o nombre de acceso) o el código EXIT exacto, conservando sus ceros iniciales. Por ejemplo 00004 no es 0004.

El bootstrap del backend añade automáticamente la columna TEXT initial_password_ciphertext de PostgreSQL al desplegar. No se copian cuentas ni claves entre desarrollo y producción.
