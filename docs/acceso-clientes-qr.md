# Acceso de clientes con QR

## Operador

En Accesos de clientes busca el código EXIT o nombre y selecciona un cliente habilitado. En Acceso con QR, Ver QR genera su código si aún no tiene uno válido y vuelve a mostrar el mismo mientras esté vigente. Descárgalo para entregarlo al cliente. Generar nuevo QR invalida el anterior; Deshabilitar QR impide nuevos accesos mediante ese código.

Cada QR corresponde a una cuenta de cliente activa. No se crean accesos QR para operadores o administradores. Si el código EXIT tiene varias cuentas activas se debe resolver la ambigüedad antes de generarlo. No se generan códigos para clientes todavía no habilitados.

## Cliente

En la pantalla de ingreso pulsa Acceder con QR y utiliza Abrir cámara, Leer imagen del QR o el enlace de acceso. También puedes escanear el QR con la cámara habitual del teléfono: el enlace abre la web e inicia la sesión. La cámara dentro de la web requiere HTTPS; por HTTP interno se puede cargar la imagen o utilizar el enlace.

El acceso con usuario y contraseña permanece disponible. El QR no omite la obligación de cambiar la contraseña inicial: si está pendiente o caducada se aplican las mismas reglas. La sesión tiene la misma duración e inactividad que una sesión con contraseña.

## Credencial

El QR permite entrar sin escribir contraseña: debe entregarse solo al cliente. Caduca a los 90 días. No contiene su contraseña. Usa un secreto aleatorio de 256 bits; el servidor guarda su hash y una copia cifrada para que el operador pueda recuperar la imagen. El enlace lleva la credencial en el fragmento y la pantalla la retira de la dirección antes de enviarla a la API. No aparece en parámetros de consulta ni en auditorías. La entrega del QR no se hace automáticamente por correo.

Deshabilitar al cliente revoca también su QR. Volver a habilitarlo exige generar/ver un QR nuevo. Revocar el QR bloquea nuevas sesiones; para cerrar también las ya abiertas hay que deshabilitar el acceso del cliente. Cambiar JWT_SECRET invalida los cifrados recuperables: genera nuevos QR.

## Base de datos y despliegue

El arranque crea la tabla customer_qr_access de forma idempotente mediante metadata.create_all. No altera usuarios existentes ni almacena QR en archivos públicos. No hay librerías nuevas de Python: se usa el generador QR de ReportLab que ya existe. El lector del navegador usa jsqr 1.4.0.

Validar en desarrollo: generar/descargar, entrar con cámara e imagen, regenerar, revocar, caducar, deshabilitar cliente y comprobar el cambio de contraseña inicial.
