# Albaranes y etiquetas de operadores

La opción «Albaranes y etiquetas» usa `fetch_customer_delivery_notes`, la misma consulta EXIT utilizada por los clientes. En la implementación actual la fuente es `dbo.AlbaranVentaCabecera` y `dbo.AlbaranVentaLineas`, no una vista nueva. Las relaciones mantienen empresa, ejercicio, serie y número. La fecha del pedido se consulta por su llave completa en `PedidoVentaCabecera`. Los datos del cliente son los conservados en la cabecera del albarán; se descubren las columnas opcionales existentes. Si no hay nombre disponible, se muestra el código del cliente.

## Acceso

Se añade el permiso `labels` («Albaranes y etiquetas») en Accesos de usuarios. Los administradores lo tienen habilitado. Los operadores con un acceso configurado deben tenerlo marcado. Se aplican las delegaciones asignadas, la sede propia y, si está concedido, «Operar en todas las delegaciones». El filtro y la generación PDF vuelven a validar el alcance contra EXIT; no se confía en las delegaciones ni el detalle enviados por el navegador. Los permisos se evalúan por empresa y delegación de la cabecera del albarán. La delegación de despacho de cada línea procede de la consulta de albaranes ya existente, con su almacén y la delegación de cabecera como referencia de respaldo.

Los listados no contienen precios. Se filtra por número solo o año/serie/número, fechas inclusivas y delegación autorizada. El listado inicial cubre los últimos 30 días y pagina de 25 en 25; no hay un truncamiento silencioso a los primeros 1.000 documentos. El orden incluye empresa para estabilizar la paginación entre empresas con números coincidentes.

## Impresión

- Tamaño único inicial: 101,6 × 76,2 mm (4 × 3 pulgadas).
- Se pueden marcar detalle, packing o ambos, y seleccionar hasta 20 albaranes por envío.
- Una etiqueta por línea inicialmente. Las copias se pueden cambiar entre 0 y 100 por línea. Cambiar las copias repite la etiqueta con la cantidad original del albarán: no divide ni modifica la cantidad de mercancía.
- El detalle contiene código real, descripción, cantidad, cliente, delegación de despacho, miniatura si está disponible, código de barras del material y código de barras del albarán. No se imprimen números de serie del producto.
- El packing incluye cliente/dirección/NIF si están disponibles, delegación, referencias y códigos de barras de pedido y albarán, sus fechas y materiales con cantidades. Cada continuación repite la cabecera. Actualmente se imprimen tres líneas de material por etiqueta para conservar legibilidad.
- Para cada albarán, primero se generan todas sus etiquetas de material y después todas sus etiquetas de packing. Un lote con varios albaranes mantiene agrupados los documentos.
- Límite de 500 etiquetas por generación. El servidor vuelve a consultar el documento y rechaza líneas que hayan desaparecido.
- PDF con fuentes incrustadas y códigos Code 128 vectoriales. Barras de tres puntos a 203 dpi cuando caben, y dos puntos en identificadores más largos. Si no cabe un código legible, se devuelve un error; no se recorta el identificador.
- Código de barras de documento: `A{empresa}/{año}/{serie}/{número}`. Pedido: `P{empresa}/{año}/{serie}/{número}`. El material codifica su SKU. Son identificadores internos, no SSCC/GS1. Una copia no representa un bulto único.

Las miniaturas siguen `PRODUCT_IMAGE_SOURCE`: imagen validada del catálogo local o consulta EXIT como respaldo según la configuración. Una imagen ausente o no decodificable no bloquea el documento: se indica «Sin miniatura».

## Impresoras

Cada usuario guarda su nombre de impresora y resolución (203, 300 o 600 dpi) en la tabla nueva `label_printer_preferences`, creada por el bootstrap habitual. No se aceptan identificadores de otros usuarios para cambiar estas preferencias.

La impresión directa requiere instalar y abrir [QZ Tray](https://qz.io/download/) en el ordenador del usuario. La web lista las impresoras instaladas en ese equipo, incluidas las impresoras de red que Windows tenga configuradas; no explora libremente toda la red. Se usa el controlador ZDesigner configurado en Windows, PDF a 4 × 3 pulgadas, sin ajuste de escala y con la densidad elegida. La aplicación confirma que el trabajo se ha enviado a la cola, no que la etiqueta haya salido físicamente.

QZ Tray puede pedir autorización para conectar e imprimir. Esta primera versión no incorpora certificados de impresión silenciosa ni claves de firma. No se desactiva la seguridad del conector. El PDF también se puede descargar e imprimir manualmente al 100 %.

## Despliegue y validación

Reconstruir backend y frontend y ejecutar el bootstrap habitual para crear la tabla de preferencias. No se modifican datos en EXIT. Habilitar el permiso en las cuentas de operador correspondientes, instalar QZ Tray en cada puesto y guardar su impresora. La impresión física y lectura con escáner deben comprobarse en la ZT410 del puesto; las pruebas automatizadas no sustituyen esa comprobación.
