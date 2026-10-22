# Entrega confirmada desde la web

La fecha de entrega y la impresión de un albarán de EXIT no confirman la recogida del cliente. El albarán acredita que el pedido está atendido; la entrega real se guarda al pulsar Entregar en Operaciones WEB, con fecha, hora, operador e historial. La API de integración no puede confirmar una entrega que no exista en la web.

Atendidos abre los últimos 30 días con todos los orígenes y conserva los pedidos entregados y facturados. El rango puede ampliarse. El reloj se cierra únicamente con delivered_at de la web. La facturación conserva su estado independiente sin inventar una entrega.

Al consultar los pedidos se retiran los antiguos eventos ENTREGADO de origen EXIT y se recupera ATENDIDO cuando no existe confirmación local. Los eventos y las fechas de entrega confirmadas en WEB se conservan. No se necesita migración de esquema ni se modifica EXIT.

Validación: prueba de albarán impreso sin entrega, corrección de estado previo, confirmación web, persistencia en Atendidos y reloj cerrado con la fecha real; suite API y compilación web.
