# Vincular, desvincular y eliminar pedidos WEB

En Operaciones → Pedidos WEB → Ver detalle:

- **Vincular EXIT**: crea primero el pedido en EXIT y después introduce en la ventana su fecha y hora reales de registro y el número EXIT, preferiblemente completo (por ejemplo `2026/AL/6007060`). Guarda el vínculo, la fecha y hora en `fecha_registro_exit` y un evento histórico REGISTRADO fechado en ese instante; también guarda la auditoría de quién lo vinculó y cuándo se realizó la acción en la web. Detiene el envío pendiente del pedido. No se generan estados de preparación o entrega que no hayan ocurrido. Comprueba que el vínculo no esté asignado a otro pedido local. La vinculación es manual y no valida la existencia del número en EXIT.
- **Pendiente**: quita el número EXIT y la fecha de registro, limpia la fecha de entrega y las cantidades servidas locales, establece PENDIENTE y reactiva los eventos existentes. El robot podrá procesarlo nuevamente. No elimina ni modifica el pedido en EXIT.
- **Eliminar**: disponible únicamente para pedidos PENDIENTE sin vínculo EXIT. Elimina el pedido local, sus líneas, historial y eventos de integración. Conserva la auditoría de la acción. No se puede deshacer desde la aplicación.

Todas las acciones piden confirmación y refrescan el listado con los filtros actuales. Solo están disponibles para operadores y administradores; pueden gestionar pedidos WEB de las delegaciones consultadas. No modifican pedidos cuyo origen sea EXIT.

API:

```text
PATCH /api/v1/store/orders/{id}/registration
{"state":"REGISTRADO","exit_order_number":"2026/AL/6007060","exit_registered_at":"2026-10-21T10:30:00+02:00"}

PATCH /api/v1/store/orders/{id}/registration
{"state":"PENDIENTE"}

DELETE /api/v1/store/orders/{id}
```

El identificador es el `public_id` del pedido WEB. No requiere cambios de esquema PostgreSQL.

La pantalla muestra «Vincular EXIT» si está Pendiente o Bloqueado y «Pendiente» para reactivar el procesamiento en los demás estados. No hay botón Reintentar: al pasar a Pendiente se habilita el procesamiento del robot y se crea el evento si falta. El número EXIT se introduce en una ventana propia de la aplicación. Entregar solo aparece en estado ATENDIDO; la API también exige ese estado.

El formulario muestra la hora Europe/Madrid y también acepta registros desde BLOQUEADO. La API interpreta fechas sin zona como hora de Madrid; con zona explícita respeta el instante recibido y lo almacena en UTC. Rechaza fechas futuras y horas inexistentes por el cambio de horario. El campo de fecha es opcional solo por compatibilidad con llamadas antiguas: en ese caso se utiliza la hora actual. Repetir el mismo vínculo, estado y fecha no duplica el histórico.

En el detalle de Pedidos WEB, **Ver historial de estados** despliega el mismo componente que usa el cliente, con las fechas y notas de cada evento. El operador puede consultarlo aunque esté desactivada la visualización del histórico para clientes. La cabecera muestra los números WEB y EXIT y la fecha de registro EXIT.
