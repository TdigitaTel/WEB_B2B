# Estados de emisión de albaranes

El estado documental del albarán se diferencia de la entrega del pedido:

- StatusImpresion activo: EMITIDO.
- Pendiente de impresión: PENDIENTE_EMISION.
- Facturación confirmada con número de factura: FACTURADO.

Se aplica a la consulta de albaranes del cliente y del operador, a las listas de albaranes vinculados y a los documentos/exportaciones generados por la web, que utilizan la misma consulta. Las pantallas reconocen también los valores antiguos ENTREGADO/IMPRESO como Emitido durante una actualización entre versiones. La cabecera de líneas deja de indicar Artículo despachado.

No se modifican los estados ni las fechas de entrega de pedidos, el botón Entregar ni el histórico del pedido. No requiere migración ni actualiza datos de EXIT.

Validación: 145 pruebas backend correctas y compilación Next.js/TypeScript correcta. Prueba específica de los tres estados de albarán. Pendiente de validación funcional en desarrollo.
