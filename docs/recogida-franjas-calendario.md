# Recogida programada y agenda diaria

El carrito muestra siempre la preparación probable, también con Datos adicionales cerrado. La inmediata conserva la lógica existente (hora actual o próxima apertura del día más minutos de preparación). En programada se puede elegir una franja local de una hora del día y sede, respetando cierres, pausas y sábados. El último tramo puede ser menor de una hora si cierra antes.

Se guardan `orders.pickup_slot_start` y `orders.pickup_slot_end` como HH:mm, junto a `pickup_date` en hora de Europe/Madrid. `attention_deadline_at` conserva el instante previsto en UTC y `preparation_minutes_snapshot` los minutos aplicados. Las columnas nuevas se añaden de forma idempotente durante bootstrap de PostgreSQL; no se modifican registros históricos.

La preparación probable es el máximo entre inicio de franja y apertura del turno más preparación. Solo se ofrecen franjas que permiten estar listo dentro de ellas. Ejemplo: apertura 08:00, preparación 60 min, franja 08–09 → previsión 09:00; franja 10–11 → previsión 10:00. Es una previsión de preparación, no una confirmación de recogida física ni de llegada del reparto.

El operador puede modificar fecha y franja desde Cambiar recogida. Se valida también en servidor y se deja historial. Una franja que deje de ser válida no se acepta al confirmar. Los pedidos anteriores sin franja mantienen su compromiso hasta edición.

Pedidos WEB → Calendario diario consulta por fecha de recogida o, en inmediatos, por fecha local de preparación prevista; no por creación del pedido. Respeta permisos de Pedidos y delegaciones. Agrupa por rango, separa inmediatos y programados sin franja. Se conservan las acciones y el detalle del gestor. La consulta no modifica pedidos ni sincroniza su estado desde EXIT. La actualización periódica sigue la configuración de actualización de pantallas.
