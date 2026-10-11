# Habilitar clientes en la web

Esta opción está en **Operaciones → Accesos de clientes** y solo está disponible para operadores y administradores.

1. Escribe el **código EXIT o el nombre** y pulsa **Buscar clientes**.
2. Pulsa **Seleccionar** en el cliente correcto.
3. Pulsa **Habilitar**. Se genera un usuario y una contraseña inicial; una cuenta ya habilitada conserva su contraseña.
4. Copia los datos y entrégalos al cliente manualmente. La clave se muestra solamente durante esta operación: no se puede recuperar después.
5. El cliente entra y debe cambiar la contraseña inicial antes de consultar productos, pedidos o documentos. Su nueva contraseña debe tener al menos 12 caracteres.

**Deshabilitar** bloquea el acceso y revoca todas sus sesiones. Si vuelves a habilitarlo, se genera otra clave inicial. Una clave caducada se renueva deshabilitando y habilitando la cuenta.

## Correo opcional

Tras habilitar aparece **Enviar por correo**. Revisa el destinatario antes de confirmar el envío. Si no hay servidor de correo configurado, utiliza la entrega manual.

El administrador configura estas variables en el archivo privado del servidor correspondiente al entorno (`dev.env` o `prod.env`). En el flujo actual están en `/opt/proyectos/WEB_B2B_INFRA/config/`. Nunca se guardan las credenciales de correo en Git:

| Parámetro | Uso |
| --- | --- |
| `INITIAL_PASSWORD_TTL_HOURS` | Vigencia de la clave inicial; 72 horas por defecto. |
| `CUSTOMER_PORTAL_URL` | Dirección que recibe el cliente; debe corresponder al entorno de su cuenta. |
| `SMTP_HOST` | Servidor de correo. |
| `SMTP_PORT` | 587 con STARTTLS, o 465 con SSL según el proveedor. |
| `SMTP_SENDER` | Remitente autorizado. |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | Credenciales del servidor de correo si necesita autenticación. |
| `SMTP_SSL` | `true` para SSL directo; `false` para STARTTLS. |

Después de cambiar la configuración hay que recrear la API mediante el despliegue del entorno. La aceptación por SMTP no garantiza que el mensaje llegue a la bandeja de entrada.

## Datos y seguridad

La búsqueda consulta clientes en EXIT por código, razón social o nombre comercial, en páginas de 50. Habilitar no modifica la ficha comercial de EXIT.

PostgreSQL conserva la cuenta en `users`: `active`, `erp_customer_code`, `password_hash`, `must_change_password` e `initial_password_expires_at`. Las contraseñas se guardan como hashes Argon2, nunca como texto. Las operaciones se registran en `audit_events` sin incluir la clave. Las sesiones revocadas están en `auth_sessions`.

El arranque añade las dos columnas nuevas de forma idempotente. Las cuentas existentes conservan su estado. Desarrollo y producción utilizan bases de datos independientes: una habilitación en desarrollo no habilita automáticamente al cliente en producción.
