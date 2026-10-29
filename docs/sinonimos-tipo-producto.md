# Sinónimos compartidos por nombre de tipo de producto

Pantalla: **Parámetros → Sinónimos de producto**. Un nombre como MACHÓN aparece una sola vez aunque exista en varias cadenas. Se agrupa ignorando acentos, mayúsculas y espacios repetidos; no se fusionan singular/plural ni nombres diferentes automáticamente.

Cada fila muestra el nombre comercial, el número de cadenas y todas las rutas con etiquetas: **Área → Categoría / familia → Subfamilia**. Esos son los tres niveles anteriores al tipo en la jerarquía actual. No se inventa un nivel adicional. Los códigos TIP-… son identificadores técnicos por cadena; siguen existiendo internamente y no encabezan la pantalla ni el nuevo Excel.

## Guardado y conservación de datos

Una sola lista de hasta 10 sinónimos por nombre de tipo, compartida por todas sus cadenas actuales y las que se añadan después con el mismo nombre normalizado. Tabla complementaria nueva `product_type_name_synonyms`, creada por el bootstrap existente; las clasificaciones y los materiales no se modifican.

Se mantienen las filas antiguas de `product_type_synonyms`. Si aún no hay lista común, se muestra y utiliza la unión de los sinónimos antiguos, eliminando solo duplicados equivalentes. Si esa unión supera diez, se conservan todos, se avisa para revisar y el editor exige elegir una nueva lista de hasta diez. No se recortan automáticamente. El Excel se bloquea hasta resolver esas listas para no omitir palabras.

El guardado comprueba un token de versión que también detecta cambios en las cadenas. PostgreSQL serializa escrituras por nombre mediante un bloqueo de transacción. Se conservan auditoría y permisos de Parámetros. Los clientes pueden buscar pero no modificar listas.

## API

- GET `/api/v1/store/product-type-synonyms`: una fila por nombre con `key`, `name`, `paths`, `synonyms`, `version` y `needs_review`.
- PUT `/group`: `{"type_name":"MACHÓN","synonyms":["niple","machones"],"version":"token recibido"}`.
- El PUT antiguo `/{id}` permite identificar una cadena, pero guarda para todo su nombre. La versión del editor ahora es un token de grupo; refrescar pantallas anteriores antes de editar.
- GET `/export.xlsx`: hoja Sinonimos, una fila por nombre, `TipoProducto`, `CadenasDeClasificacion` y `Sinonimo1` a `Sinonimo10`; hoja Cadenas con el detalle de las rutas.
- POST `/import`: revisión/guardado y añadir/reemplazar igual que antes; identifica el tipo por su nombre. Reconoce códigos del formato anterior para localizar el grupo, pero rechaza filas repetidas del mismo nombre: descargar la nueva plantilla para tener una fila por tipo.

Las cargas son atómicas: si hay errores, no se guarda ningún cambio. Se mantienen límites de 10.000 filas, 5 MB comprimidos y 50 MB descomprimidos, y rechazo de fórmulas y duplicados.

## Búsquedas

Los sinónimos resuelven los artículos asociados a todas las cadenas del nombre común. Se conserva la coincidencia de la expresión completa más larga y las palabras adicionales/material/medida. La consulta de EXIT mantiene filtros de clasificación y categorías visibles, marcas, estado activo, conteos y paginación. Los códigos se transfieren en bloques de 1.000.

## Validación

Pruebas de agrupación de tres cadenas, unión de datos anteriores, conservación de más de diez palabras para revisión, guardado común, concurrencia de versión, nueva cadena que hereda palabras, Excel agrupado y hoja de rutas, carga atómica, permisos y búsqueda de materiales de las tres cadenas desde catálogo y sugerencias. Vista y guardado revisados en navegador con datos locales de ejemplo. Pendiente verificar con la clasificación real al desplegar en desarrollo.
