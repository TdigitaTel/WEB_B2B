# Sinónimos por tipo de producto

Pantalla: **Parámetros → Sinónimos de producto**. Requiere permiso de Parámetros y rol operador o administrador. El cliente puede buscar por sinónimos pero no gestionar las listas.

## Uso

- Buscar por código, tipo, clasificación o sinónimo; filtro de tipos sin sinónimos.
- Editar un tipo: hasta 10 palabras o expresiones de 1 a 100 caracteres. Campos vacíos eliminan entradas al guardar. No admite duplicados ignorando acentos y mayúsculas, ni comodines.
- Descargar Excel / plantilla: un tipo por fila, código conservado como texto, clasificación informativa y columnas Sinonimo1 a Sinonimo10.
- Cargar Excel: revisar primero, mostrar errores y guardar todos los cambios solo si todas las filas son válidas. Máximo 10.000 filas, 5 MB comprimidos y 50 MB descomprimidos. Se rechazan fórmulas y códigos desconocidos o repetidos.
- Modo por defecto **Añadir**: conserva existentes y añade nuevos, sin duplicados; celdas vacías no borran. **Reemplazar**: sustituye la lista de los tipos incluidos y permite vaciarla; no modifica tipos omitidos.

La carga desde archivos es explícita desde la web o mediante el endpoint autenticado; no hay vigilancia de carpetas ni generación de palabras por IA.

## API y persistencia

- GET `/api/v1/store/product-type-synonyms`: tipos de la clasificación con lista y versión.
- PUT `/{id}`: `{"synonyms":["llave de paso"],"version":0}`. Versión opcional para integraciones, enviada siempre por el editor web; conflicto 409 si cambió desde su lectura.
- GET `/export.xlsx`: libro actual, también plantilla de carga.
- POST `/import`: multipart `file`, `mode=merge|replace`, `apply=false|true`. Revisar no escribe. Guardar vuelve a validar con los datos vigentes, bloquea tipos en orden y realiza una transacción; sin cambios parciales si hay errores.

Tabla PostgreSQL complementaria `product_type_synonyms`, clave `product_type_id` hacia `material_product_types`, lista JSON, versión y fechas. El arranque existente (`bootstrap`) crea la tabla con `create_all`; no requiere ejecutar SQL manualmente. No se modifica EXIT. Los guardados y las cargas quedan auditados.

## Búsqueda

Catálogo y sugerencias conservan la búsqueda textual habitual y añaden una alternativa por materiales asociados al tipo cuando se reconoce una expresión completa. Se ignoran acentos y mayúsculas. Se prioriza la expresión más larga y, si se repite en varios tipos, se incluyen los materiales de todos esos tipos. No se aplican coincidencias parciales dentro de una palabra.

Ejemplo: «llave de paso latón 1/2» busca también los materiales del tipo asociado a «llave de paso», conservando «latón 1/2» como restricciones. Se mantienen categorías visibles, filtros de clasificación, marcas habilitadas, estado activo de EXIT, conteos y paginación. No exige stock positivo por tratarse de una búsqueda con texto.

Los códigos asociados se pasan a una tabla temporal de SQL Server en bloques de 1.000, sin una consulta a EXIT por artículo. No se duplican artículos por coincidir en texto y tipo.

## Validación

Pruebas de edición, persistencia, límite y duplicados, versión, carga atómica, añadir/reemplazar, códigos como texto, Excel, permisos de módulo, resolución de expresiones, llamadas desde catálogo y sugerencias y SQL parametrizado con 1.001 códigos, filtros y paginación. Vista local verificada con datos de ejemplo. Pendiente comprobar las búsquedas con EXIT real tras desplegar en desarrollo.
