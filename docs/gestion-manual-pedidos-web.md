# Vincular, desvincular y eliminar pedidos WEB

En Operaciones → Pedidos WEB → Ver detalle:

- **Marcar registrado / Vincular EXIT**: introduce el número EXIT, preferiblemente completo (por ejemplo `2026/AL/6007060`). Guarda el vínculo y el estado REGISTRADO; detiene el envío pendiente del pedido. Comprueba que el vínculo no esté asignado a otro pedido local. La vinculación es manual y no valida la existencia del número en EXIT.
- **Marcar pendiente / Desvincular EXIT**: quita el número EXIT y la fecha de registro, limpia la fecha de entrega y las cantidades servidas locales, establece PENDIENTE y reactiva los eventos existentes. El robot podrá procesarlo nuevamente. No elimina ni modifica el pedido en EXIT.
- **Eliminar pedido**: disponible únicamente para pedidos PENDIENTE sin vínculo EXIT. Elimina el pedido local, sus líneas, historial y eventos de integración. Conserva la auditoría de la acción. No se puede deshacer desde la aplicación.

Todas las acciones piden confirmación y refrescan el listado con los filtros actuales. Solo están disponibles para operadores y administradores; pueden gestionar pedidos WEB de las delegaciones consultadas. No modifican pedidos cuyo origen sea EXIT.

API:

```text
PATCH /api/v1/store/orders/{id}/registration
{"state":"REGISTRADO","exit_order_number":"2026/AL/6007060"}

PATCH /api/v1/store/orders/{id}/registration
{"state":"PENDIENTE"}

DELETE /api/v1/store/orders/{id}
```

El identificador es el `public_id` del pedido WEB. No requiere cambios de esquema PostgreSQL.
