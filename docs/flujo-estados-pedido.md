# Flujo de estados y fechas

Se conserva el resumen de estado actual y avance en la cabecera. Al abrir el
pedido aparece «Estado del pedido» con el flujo visible y sus fechas, también
cuando existe resumen de recogidas. Se aplica a cliente, Pedidos WEB del operador
y seguimiento compartido. En escritorio ocupa cinco columnas y en móvil una
cronología vertical sin desplazamiento horizontal.

Las cinco etapas principales son Pendiente, En procesamiento, Pendiente de
recogida, Entregado y Facturado. Parcial/Total son subestados dentro de recogida
y entrega, nunca etapas adicionales. Se destaca la etapa actual; cada fecha
procede de un registro, sin completar automáticamente las etapas anteriores.
La factura conserva su fecha sin inventar hora. La fecha de entrega se toma del
registro de recogidas cuando existe: facturar o imprimir un albarán no acredita
una entrega total. Las entregas históricas sin desglose no muestran una falsa
fecha de entrega física. Si falta una fecha se indica «Sin fecha registrada».

El seguimiento público añade solamente estados y fechas permitidos, sin notas,
autores o datos de cliente. No cambia estados, cantidades, permisos de edición
ni reglas de recogida. Sin migraciones ni dependencias nuevas.
