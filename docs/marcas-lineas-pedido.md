# Marcas por artículo de pedido

Cada fila de las listas de cliente y operador muestra checks de solo lectura: Generado en WEB, Ingresado en EXIT, Eliminado en EXIT. Una línea eliminada indica «No se va a atender». No son controles para editar el pedido.

`order_items.created_in_web` se fija al crear la línea: verdadero en checkout WEB, falso al importar una línea adicional de EXIT. `exit_entered_at` conserva la primera confirmación mediante un detalle completo leído correctamente de EXIT. Vincular únicamente la cabecera no confirma sus líneas. `exit_removed_at` conserva la baja y se limpia si reaparece la misma línea; la primera confirmación permanece. Las cantidades, precios, identificadores, fechas y observaciones originales se conservan. La llave de cuatro campos sigue normalizada en la cabecera y las líneas la referencian mediante order_id.

Los campos nuevos se crean con bootstrap, sin migración manual. Para registros anteriores, el origen puede no conocerse: se muestra un check mixto con «sin registro», sin atribuir a WEB líneas que pudieron añadirse desde EXIT. No se inventa una fecha histórica de entrada: se confirma en la siguiente sincronización completa. Los emparejamientos ambiguos y los fallos de consulta no generan confirmaciones ni bajas.
