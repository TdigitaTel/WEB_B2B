# Origen de las líneas de pedido

La columna única WEB/Tienda muestra exclusivamente `OrderItem.created_in_web`:
marcado y texto WEB cuando es verdadero; sin marcar y texto Tienda cuando es falso.
Por criterio del usuario, los registros históricos sin marca WEB (nulos o sin
campo) se muestran como Tienda, con el check sin marcar. No existe un tercer
estado visual «Sin confirmar». `entered_in_exit` no interviene en esta presentación:
sincronizar una línea nunca cambia su origen.

Las líneas eliminadas se mantienen íntegramente: fondo suave, borde lateral,
descripción tachada y aviso «Eliminado · No se va a atender». No hay columna ni
check de eliminación. Se aplica en cliente, operador WEB, listas de preparación,
planificación y seguimiento público. La marca de origen se conserva también en
las líneas eliminadas; no se alteran sus cantidades, importes o historial.

El SKU 23568 se añade a la corrección histórica confirmada del pedido
WEB-2026-0000321 / 2026-AL-6008552, cliente 11264. El bootstrap existente aplica
la corrección con auditoría y de forma idempotente. No se actualizan otros pedidos
con el mismo SKU ni se atribuyen automáticamente a WEB todas sus líneas.

Comprobación: pruebas de reparación delimitada y seguimiento del servidor;
`test:preserve-exit-lines`, `test:order-tracking`, `test:order-planning`,
`test:order-pickups`, `test:pickup-summary` y compilación del frontend.
