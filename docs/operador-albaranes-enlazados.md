# Albaranes del pedido en Operaciones

Los pedidos WEB del operador utilizan el mismo componente de enlaces que Mis pedidos: un albarán muestra su número como enlace directo; varios abren el listado con enlaces individuales. Cada enlace abre el documento dentro de Operaciones, con fecha, estado y líneas económicas.

La consulta por lotes de albaranes exige ejercicio/serie/número, pero algunos pedidos guardan solamente NumeroPedido. Cuando no hay coincidencia, se consulta por cliente como en Mis pedidos y se comprueba número y año de registro del pedido. No se modifica la referencia guardada ni se cambia el estado de entrega física.

El detalle se consulta en GET /api/v1/store/orders/{order_id}/delivery-note?number=... para operadores y administradores. El cliente se toma del pedido, no del navegador. Se exige vínculo con el pedido y se rechazan documentos de otro pedido o año. Un fallo de consulta muestra error en vez de un contador cero confirmado.

Validación: 130 pruebas backend correctas, compilación Next.js/TypeScript correcta y prueba de enlaces único/múltiple correcta. Sin migración PostgreSQL. Pendiente de validación funcional en desarrollo con el pedido real.
