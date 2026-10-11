# Confirmar la entrega de un pedido WEB

En **Operaciones → Pedidos WEB**, busca el pedido con los filtros, abre **Ver detalle** y pulsa **Marcar entregado**. Confirma únicamente cuando el material se haya entregado al cliente.

La aplicación registra la fecha y hora del servidor en `orders.delivered_at` (PostgreSQL `TIMESTAMPTZ`) y el operador en el historial/auditoría. La pantalla muestra la hora local del navegador. No se solicita una fecha manual y confirmar nuevamente no cambia la primera fecha registrada.

El estado pasa a **ENTREGADO** y el listado se actualiza; si estaba filtrado por pendientes, el pedido desaparece de ese filtro y se consulta en **Entregado**. Un pedido ya facturado conserva **FACTURADO**. Las consultas y sincronizaciones de EXIT conservan la confirmación de entrega de la web. Esta acción registra la entrega en nuestra base de datos, sin modificar directamente EXIT.

Solo operadores de la delegación del pedido y administradores pueden confirmarla. Los clientes no pueden marcar sus propios pedidos. La columna nueva se crea automáticamente en el despliegue, sin inventar fechas para pedidos anteriores.
