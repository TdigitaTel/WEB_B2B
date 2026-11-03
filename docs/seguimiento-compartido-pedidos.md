# Seguimiento compartido de pedidos

## Operador

En el detalle de un pedido WEB, pulsar **Compartir seguimiento** y **Crear enlace privado**. Se puede copiar el enlace o un mensaje listo para pegar en WhatsApp. No se realiza ningún envío automático ni se requiere una integración con WhatsApp.

El enlace dura 30 días. **Desactivar enlace** lo invalida inmediatamente; **Crear nuevo enlace** invalida los anteriores del pedido. Al cerrar el diálogo no se conserva el secreto recuperable: si ya había un enlace activo se puede desactivarlo o crear uno nuevo.

## Destinatario

Abre `/seguimiento#token=…` sin iniciar sesión. Ve únicamente referencia WEB/EXIT, estado, fecha prevista de cabecera y por artículo, cantidades pedidas/servidas y situación de disponibilidad. No se exponen precios, cliente, contactos, direcciones, notas libres, documentos ni acciones de edición. El estado se consulta periódicamente con el intervalo global configurado, sin vaciar la vista durante las consultas. La revocación se comprueba en cada consulta; si caduca o se revoca, se retira el pedido de la vista abierta al siguiente refresco.

El estado EXIT se contrasta usando empresa, ejercicio, serie y número. La recogida física confirmada en la web se distingue del material servido en EXIT. Si la fuente no responde se muestra una advertencia y la información guardada disponible.

## API y almacenamiento

- `GET /api/v1/store/orders/{id}/tracking-link`: estado/caducidad, operador autorizado en la delegación.
- `POST /api/v1/store/orders/{id}/tracking-link`: crea un secreto y revoca enlaces previos. No admite borradores.
- `DELETE /api/v1/store/orders/{id}/tracking-link`: revoca los enlaces del pedido.
- `POST /api/v1/order-tracking/read`: consulta pública con `{ "token": "…" }`, sin sesión ni capacidad de modificar el pedido.

La tabla `order_tracking_links` conserva únicamente SHA-256 del secreto aleatorio de 256 bits, pedido asociado, operador creador y fechas de creación/caducidad/revocación. El secreto no se guarda en texto claro ni se registra en auditoría. Se devuelve una sola vez al crearlo. La URL usa un fragmento, que no viaja al servidor al abrir la página ni en el referente; la consulta API lo envía en el cuerpo. Respuestas sin caché y página sin indexación ni referente. Quien tenga el enlace puede consultar ese pedido mientras esté activo.

`bootstrap` crea la tabla automáticamente, sin migración manual adicional ni nuevas dependencias. Los pedidos y sus líneas no se borran ni cambian al generar, revocar o consultar un enlace. Esta función permite compartir por cualquier canal; no identifica a la persona que abre el enlace.

## Comprobaciones

Pruebas de creación y lectura anónima, permisos/delegaciones, datos excluidos, hash, sustitución, revocación, caducidad, pedido único y consulta EXIT por llave completa. Pruebas React del diálogo, mensaje copiable, vista de solo lectura y limpieza al revocar; compilación de producción. Validación local con fuentes simuladas, pendiente de contraste tras desplegar en desarrollo.
