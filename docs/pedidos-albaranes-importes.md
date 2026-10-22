# Albaranes e importes del pedido EXIT

En Mis pedidos, el detalle de un pedido registrado en EXIT muestra un enlace directo si tiene un albarán, o un botón Albaranes con la lista de números individuales si tiene varios. Cada enlace abre Albaranes y facturas filtrado por ese número, sin limitar la búsqueda al último mes. Respeta el permiso para consultar albaranes.

Las líneas de EXIT incluyen Precio, %Descuento, ImporteNeto e ImporteLiquido (Total). Se conserva el importe cero en vez de sustituirlo por cantidad × precio. ImporteNeto es opcional y no se calcula si EXIT no lo proporciona. Las columnas económicas adicionales se muestran para pedidos registrados en EXIT; en móvil se consultan desplazando horizontalmente. La protección de precios también filtra los nuevos campos.

No requiere migración PostgreSQL: los valores nuevos se consultan en vivo en EXIT. Los pedidos locales sin proyección EXIT no tienen un importe neto inventado.

Validación: 127 pruebas backend correctas, compilación Next.js/TypeScript correcta, prueba de interacción del enlace único y de los enlaces del diálogo múltiple correcta. Pendiente de comprobación funcional en desarrollo con documentos reales.
