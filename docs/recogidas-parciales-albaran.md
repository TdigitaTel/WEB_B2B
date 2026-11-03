# Recogidas parciales por albarán y líneas

El operador pulsa «Registrar recogida», selecciona uno o varios albaranes o sus líneas completas y confirma. No introduce cantidades: se toman del detalle de EXIT. Cada confirmación guarda operador, fecha, observación opcional y sus líneas. No escribe en EXIT ni genera pedidos ni albaranes.

## Estados operativos

Se conserva `estado_registro_exit` como estado de la integración. El nuevo `pickup_summary.state` calcula la situación real de recogida:

- `EN_PREPARACION`: sin material disponible para recoger ni recogidas registradas.
- `PENDIENTE_RECOGIDA_PARCIAL`: hay material disponible, pero todavía no está preparado todo lo pendiente.
- `PENDIENTE_RECOGIDA_TOTAL`: todo lo que queda pendiente está disponible, aunque ya existan entregas anteriores.
- `ENTREGADO_PARCIAL`: se recogió material y sigue faltando, sin otro material listo actualmente.
- `ENTREGADO_TOTAL`: las cantidades de todas las líneas activas están recogidas.
- `SIN_MATERIALES_ACTIVOS`: todas las líneas están retiradas o no hay líneas.
- `REVISAR_ENTREGA_HISTORICA`: existe una fecha global antigua sin eventos que permitan atribuirla a albaranes; no se inventa su desglose ni se permite volver a entregar por error.

Los contadores son por material/línea completa; internamente se comparan cantidades y unidades para no dar por entregado un material repartido entre varios albaranes. Las líneas eliminadas en EXIT se excluyen de los totales y de la selección. La facturación aparece como dato separado y no acredita la recogida. La primera preparación parcial no cierra el plazo del conjunto. Si no se conoce la hora de preparación completa no se inventa un tiempo de atención.

## Persistencia normalizada

Bootstrap crea `order_delivery_notes`, `order_delivery_note_lines`, `order_pickups` y `order_pickup_lines`, y añade `orders.pickup_managed_at`. Las claves de empresa/ejercicio/serie/número del pedido permanecen en `orders`. Cada albarán tiene su propia llave de cuatro campos única; sus líneas apuntan al artículo de pedido por FK. Cada línea de recogida apunta a su evento y a una línea de albarán única, con la cantidad confirmada como evidencia inmutable. No se eliminan documentos ni líneas si desaparecen de EXIT; dejan de estar disponibles y conservan las recogidas previas. Un pedido con recogidas no puede desvincularse ni cambiar de llave EXIT. Tampoco se oculta únicamente porque el pedido desaparezca de EXIT si existe evidencia local de recogida.

El vínculo de una línea usa su identificador de pedido si la fuente lo proporciona; con el contrato EXIT actual se acepta el artículo y unidad solo cuando identifican una única línea del pedido. Las coincidencias ambiguas, unidades diferentes, cantidades no positivas o albaranes modificados después de recogerse quedan en revisión. Falta contrastar en EXIT real el campo que identifica la línea original para automatizar las coincidencias repetidas; no se supone que `Orden` del albarán sea la línea del pedido.

## API y seguridad

- GET `/api/v1/store/orders/{id}/pickups`: documentos, selección disponible, resumen e historial; solo operador/admin con acceso a esa delegación.
- POST misma ruta: `request_id` UUID, `expected_version`, `line_ids` y `observation` opcional. La versión viene del GET. No acepta una cantidad introducida por el operador.
- La confirmación vuelve a leer el pedido por su llave y comprueba cliente, detalle completo, albaranes actuales, versión, bajas, líneas disponibles y cantidades. Bloquea cantidades superiores a lo pedido.
- Bloqueo de cabecera y unicidad por línea evitan dos recogidas simultáneas; `request_id` permite reintentar una respuesta perdida sin duplicarla. Una selección diferente requiere otro identificador.
- POST `/api/v1/store/orders/delivery` ya no confirma el pedido completo: devuelve 409 para que clientes antiguos usen el flujo por albarán. La transición manual global a ENTREGADO también queda bloqueada para pedidos WEB.
- Cliente, panel de inicio y seguimiento compartido muestran los resúmenes; no pueden confirmar recogidas. El seguimiento público calcula con documentos actuales en memoria, sin escribir en la BD ni exponer el operador o las observaciones de las recogidas.

Las lecturas de albaranes se filtran en SQL por las cuatro claves de los pedidos, por bloques de hasta 200 claves, y se reutilizan por cliente dentro de cada petición. Un resultado truncado o un fallo de EXIT impide confirmar y conserva el historial. Los resúmenes del historial se pueden consultar en bloque. No hay cambios de dependencias.

## Validación y límites

Pruebas locales con SQLite y fuentes EXIT simuladas: ciclo 4+3+3 de un material, selección por línea, dos unidades de medida, exclusión de bajas, albaranes desaparecidos/cambiados, permisos, facturación independiente, idempotencia, versión, filtros, SQL parametrizado y seguimiento público sin escrituras. La web prueba selección completa, líneas no disponibles, ausencia de cantidades editables, reintento, historial y actualización. Pendiente validar en desarrollo con SQL Server/PostgreSQL y albaranes reales, incluyendo artículos repetidos y devoluciones. Las devoluciones no revierten automáticamente una recogida física ya confirmada: requieren revisión.

### Resumen compacto

El resumen compartido por cliente, operador y seguimiento público muestra el estado y el porcentaje de materiales recogidos con una barra. «Información avanzada» despliega preparación, disponibilidad, recogidos, pendientes, última recogida y avisos. El detalle empieza cerrado, conserva su apertura durante el refresco y su botón no abre/cierra la ficha del pedido. El cálculo y los estados permanecen intactos; sin materiales activos no se muestra un porcentaje inventado.
