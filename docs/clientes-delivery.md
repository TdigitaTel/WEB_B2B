# Delivery por cliente

En Accesos de clientes, buscar y seleccionar el código EXIT. En Modalidad de entrega, marcar Permitir delivery y guardar. Por defecto está desactivado.

La autorización se guarda en PostgreSQL por código EXIT y la comparten la cuenta principal y sus subusuarios. No modifica EXIT ni sus datos comerciales. Solo OPERADOR_TIENDA y ADMIN pueden cambiarla; el servidor valida que el cliente existe en EXIT y registra auditoría.

En Datos adicionales del carrito, un cliente autorizado puede elegir Recogida en tienda o Delivery e indicar una dirección. La modalidad y la dirección quedan guardadas en el pedido, visibles al cliente y a operaciones, e incluidas en el aviso de integración. Si no está autorizado no se muestra Delivery y la API rechaza intentos de usarlo, incluso al enviar un borrador después de revocar el permiso. Pedidos anteriores siguen como recogida.

La etiqueta Atención prevista y el retraso miden preparación hasta ATENDIDO, también con delivery. La entrega real sigue siendo otro dato, confirmado en la web. No se calcula tiempo de transporte ni tarifa de reparto.

El arranque crea customer_delivery_settings y añade de forma idempotente fulfillment_method y delivery_address a orders. No requiere SQL manual. Revertir la aplicación conserva estos datos adicionales.

La cabecera muestra Recogida en tienda por defecto y Recogida real para su confirmación. Solo un pedido solicitado como DELIVERY muestra Delivery y Entrega real.

En Operaciones, Pendiente solo está habilitado desde REGISTRADO y la API rechaza otros estados sin cambiar el vínculo EXIT. Entregar se muestra en la cabecera solo en ATENDIDO y sin entrega confirmada; no se mezcla con Gestión.
