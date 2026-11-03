# Entrega histórica confirmada: 6007768

El usuario confirma la entrega total de WEB-2026-0000260, cliente 11264, pedido EXIT (empresa 1, ejercicio 2026, serie AL, número 6007768). Albarán 2026/AL/682017735: línea 5 artículo 21679 y línea 10 artículo 23538, una UD cada una. La web ya conserva `orders.delivered_at`: 26/10/2026 16:38, horario de Madrid.

La regularización de bootstrap comprueba la llave completa, cliente, fecha, historial WEB con operador y ambas líneas. Crea el desglose de recogida usando fecha y operador originales. No cambia facturación, cantidades del pedido, precios ni la fecha histórica. No deduce entrega a partir de FACTURADO. Un caso diferente, un dato ambiguo o un pedido con nuevas recogidas no se modifica. Se registra auditoría y se evita repetir la operación.

**Almacén de datos: PostgreSQL de la web.** `orders.delivered_at` es la fecha de entrega total, no un booleano. El detalle normalizado está en `order_pickups` (`order_id`, `confirmed_at`, `confirmed_by`) y `order_pickup_lines` (`pickup_id`, `delivery_line_id`, `quantity`). Esta última enlaza con `order_delivery_note_lines.id`, que identifica la línea del albarán. ENTREGADO_TOTAL se calcula con esas recogidas; no se debe forzar `orders.estado_registro_exit` si el pedido está facturado.

Consulta previa sin escritura: `python -m app.repair_historical_pickup`. Aplicación explícita: añadir `--apply`. El despliegue habitual también la ejecuta mediante bootstrap. Si faltan datos, devuelve skipped y deja todo intacto.

Se ha inspeccionado la pantalla real en modo consulta. **No se han cambiado datos de producción desde el desarrollo local**; la corrección se aplica al desplegar o ejecutar la herramienta en la base correspondiente.
