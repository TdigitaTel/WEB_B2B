# Recogida programada y agenda diaria

El carrito muestra siempre la preparación probable, también con Datos adicionales cerrado. La inmediata conserva la lógica existente (hora actual o próxima apertura del día más minutos de preparación). En programada se puede elegir una franja local de una hora del día y sede, respetando cierres, pausas y sábados. El último tramo puede ser menor de una hora si cierra antes.

Se guardan `orders.pickup_slot_start` y `orders.pickup_slot_end` como HH:mm, junto a `pickup_date` en hora de Europe/Madrid. `attention_deadline_at` conserva el instante previsto en UTC y `preparation_minutes_snapshot` los minutos aplicados. Las columnas nuevas se añaden de forma idempotente durante bootstrap de PostgreSQL; no se modifican registros históricos.

La preparación probable es el máximo entre inicio de franja y apertura del turno más preparación. Solo se ofrecen franjas que permiten estar listo dentro de ellas. Ejemplo: apertura 08:00, preparación 60 min, franja 08–09 → previsión 09:00; franja 10–11 → previsión 10:00. Es una previsión de preparación, no una confirmación de recogida física ni de llegada del reparto.

El operador puede modificar fecha y franja desde Cambiar recogida. Se valida también en servidor y se deja historial. Una franja que deje de ser válida no se acepta al confirmar. Los pedidos anteriores sin franja mantienen su compromiso hasta edición.

Pedidos WEB → Calendario diario consulta por fecha de recogida o, en inmediatos, por fecha local de preparación prevista; no por creación del pedido. Respeta permisos de Pedidos y delegaciones. Agrupa por rango, separa inmediatos y programados sin franja. Se conservan las acciones y el detalle del gestor. La consulta no modifica pedidos ni sincroniza su estado desde EXIT. La actualización periódica sigue la configuración de actualización de pantallas.


## Vista semanal

El calendario se abre por defecto en Pedidos WEB y muestra de lunes a domingo de la semana actual en Europe/Madrid. Todos los días aparecen aunque estén vacíos, con franjas y número de pedidos. Cada pedido se coloca en su celda de día y hora; al pulsarlo se abre el detalle del listado, con sus acciones. Desde/Hasta admite entre uno y siete días inclusive; el servidor también rechaza rangos mayores, invertidos o incompletos. Semana actual restablece la semana en curso. Los filtros del listado se ocultan en calendario para no confundir fechas de creación con previsiones. La delegación sigue aplicándose. La consulta antigua por `day` sigue disponible para compatibilidad.


## Previsión vigente, navegación y selección visible

La fecha de agenda se obtiene de `attention_deadline_at` en Madrid, o de `pickup_date` si aún no existe previsión. Nunca se usa la creación ni la entrega física. Si el operador mueve la previsión a otro día, el pedido se mueve en la agenda; no se aplica la franja antigua al nuevo día. La API etiqueta la fuente como PICKUP_WINDOW, EXPECTED o DATE_ONLY. Las franjas reservadas se diferencian de agrupaciones por hora estimada.

Cada pedido del calendario abre su ficha en Listado y la enfoca, incluso fuera del filtro de creación habitual. Se muestra que es una selección del calendario y se puede volver al listado completo. La ficha mantiene las acciones y puede refrescarse con la consulta individual de operador, respetando su delegación y permiso de Pedidos.

Los errores estructurados de validación se presentan como texto legible. Si una API anterior exige `day`, se consultan los días del rango como compatibilidad y se avisa de que debe completarse la actualización para incluir previsiones modificadas. No se afirma que haya cero pedidos cuando falla la consulta.

Carrito y Cambiar recogida ofrecen radios Inmediata / Fecha programada. En el carrito, Inmediata permanece visible pero desactivada si no está disponible; el operador conserva la posibilidad de forzarla con la confirmación ya existente.


## Cuadrícula de calendario

La vista semanal es una tabla con días en columnas y horas de inicio en filas, con cabecera y eje horario fijos al desplazarse. No duplica fichas grandes debajo del calendario. Cada evento muestra horario exacto, número, cliente y estado; el clic mantiene la apertura del detalle en Listado. Las franjas reservadas son violetas y las horas estimadas azules. Los eventos que coinciden se apilan sin ocultarse; se amplía el eje para horarios anteriores o posteriores al tramo habitual. Sin hora confirmada se muestra en una fila propia. Las franjas no alineadas a la hora se sitúan en la fila de su hora de inicio y conservan su rango exacto en el texto. En móvil la cuadrícula se desplaza horizontalmente, manteniendo la relación día/hora.
