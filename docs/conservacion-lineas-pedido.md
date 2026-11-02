# Conservación de líneas del pedido WEB

La sincronización de EXIT ya no borra ni recrea `order_items`. Cliente y operador leen el mismo detalle persistido. La clave del pedido (empresa, ejercicio, serie y número) permanece en `orders`; cada línea conserva su ID y su número de línea EXIT, sin duplicar la clave de cabecera.

## Comportamiento

- Se conservan las cantidades pedidas, descripción, unidad, precios y ajustes manuales de las líneas existentes. EXIT actualiza las cantidades servidas/pendientes y la zona de preparación.
- Si una lectura completa y correcta del detalle no incluye una línea guardada, se registra `order_items.exit_removed_at`. La fila sigue en la BD y en ambas vistas con «Eliminada en EXIT». Se conservan las últimas cantidades observadas y las previsiones históricas.
- Las líneas retiradas tienen pendiente operativo cero en planificación; no se generan propuestas de entrega nuevas para ellas. Las previsiones y observaciones manuales anteriores no se borran.
- Si reaparece la misma línea EXIT con el mismo artículo, se reutiliza su ID y se limpia el aviso. Una línea nueva se incorpora sin reemplazar las anteriores.
- La identificación principal es el número de línea dentro del pedido. Las líneas antiguas sin número se vinculan por artículo solo si no hay ambigüedad (o por correspondencia completa de datos en un grupo repetido). Si no puede determinarse qué línea repetida corresponde, se conserva el grupo sin inventar bajas ni duplicados.
- Una integración que omite `lines` no altera el detalle; `lines: []` significa una lectura completa sin líneas. Los fallos de consulta no cambian los estados. Una respuesta con números de línea duplicados se rechaza antes de alterar las líneas.

## Instalación y límites

`bootstrap` añade de forma idempotente `exit_removed_at TIMESTAMPTZ` a PostgreSQL; las bases nuevas lo incluyen en el modelo. No se han tocado datos de producción. Esta protección evita pérdidas futuras; no puede reconstruir por sí sola líneas borradas antes de instalarla, que requieren una copia de seguridad u otra fuente fiable.

La conciliación de cabeceras es independiente: este cambio trata exclusivamente la conservación del detalle. Las acciones explícitas de borrar pedidos o carritos mantienen su comportamiento actual.

## Validación

Pruebas de importación y consulta de cliente/operador: conservación de IDs, datos y planificación, baja/recuperación, reintentos, detalle vacío/omitido, SKU repetido, respuesta ambigua y fallo de EXIT. Prueba de presentación del aviso y compilación de producción del frontend.
