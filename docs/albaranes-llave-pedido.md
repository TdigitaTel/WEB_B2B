# Albaranes vinculados por la llave completa del pedido

El enlace se comprueba con **CodigoEmpresa + EjercicioPedido + SeriePedido + NumeroPedido**. No se relacionan albaranes solo por número, ni por ejercicio/serie/número omitiendo empresa.

Las consultas de cabeceras de albaranes incluyen CodigoEmpresa y los tres campos del pedido. El API devuelve `company_code`, `exit_company_code`, `exit_order_year`, `exit_series`, `exit_order_number`. La referencia formateada `order_number` se conserva para mostrarla y para consumidores anteriores; se acepta como representación de los tres componentes únicamente si también llega la empresa. Nunca se deduce esta de la pantalla o del primer pedido encontrado.

La llave del pedido guardado es la definida en `orders`: empresa existente y los campos separados de ejercicio/serie/número. Las referencias antiguas completas se pueden leer junto a su empresa conocida; un número antiguo sin ejercicio/serie no basta. Si falta parte de la llave hay que completarla desde Operaciones o mediante el robot. La serie vacía es válida si está informada como tal; no equivale a dato desconocido.

## Consultas y documentos

- La consulta de estados por lote recibe tuplas de cuatro componentes y filtra también CodigoEmpresa en SQL parametrizado. Procesa todos los pedidos en bloques de 400, por debajo del límite de parámetros de SQL Server; no corta la lista a 1.000 pedidos.
- Mis pedidos y Operaciones agrupan albaranes y actualizan estados solo por una coincidencia de la llave completa.
- Al abrir un albarán desde Operaciones se comprueba de nuevo la pertenencia al pedido, incluyendo empresa. No se devuelve otro homónimo.
- Al abrirlo desde Mis pedidos se envía el `order_id` de la web a GET `/api/v1/delivery-notes`. El servidor comprueba cliente y permisos de pedidos propios y filtra por la llave completa. La exportación ALBARAN admite ese mismo `order_id` para conservar el contexto.
- El identificador opaco `id` de los albaranes incorpora ahora la empresa; usar el ID que devuelve el API al construir el enlace de archivo. El número visible no cambia. Actualizar listados abiertos antes del despliegue.
- Las líneas se agrupan por la llave del propio albarán, incluyendo CodigoEmpresa, para evitar mezclar líneas de documentos homónimos entre empresas. Las uniones SQL ya incluyen empresa, ejercicio, serie y número de albarán.

No se crean tablas ni se duplican datos: los albaranes se consultan en EXIT y su relación se compara con la llave normalizada del pedido. No se escribe en EXIT ni se reescriben estados históricos automáticamente.

## Validación

Pruebas con base desechable y consultas simuladas: rechazo de empresa ausente o distinta; ejercicio, serie y número diferentes; pedido incompleto; agrupación de líneas en dos empresas con igual número de albarán; bloqueo de apertura indebida; estados del cliente sin contaminación entre empresas; apertura/exportación con contexto del pedido y rechazo de un pedido ajeno; consulta por lotes de 1.001 pedidos. Pruebas existentes ajustadas para que las fuentes indiquen empresa explícitamente. Compilación web y TypeScript. Pendiente comprobar las consultas y documentos con SQL Server real tras desplegar en desarrollo.
