# Buscador y sinónimos

Parámetros tiene una única entrada «Buscador y sinónimos», con tipos/sinónimos, materiales, palabras generales y un probador. Los cambios pendientes se conservan al alternar las pestañas internas. Las familias siguen en su pantalla separada con sus filtros.

## Regla acordada

Un tipo general y sus sinónimos se omiten si aparece un material reconocido o un tipo específico. Sin ellos, el tipo general limita la clasificación. Ejemplos con ACCESORIO general, «complemento» como sinónimo suyo y «niple» como sinónimo de MACHÓN:

| Búsqueda | Clasificación | Otras condiciones |
| --- | --- | --- |
| accesorio | ACCESORIO | — |
| accesorio de cocina | ACCESORIO | cocina |
| accesorio de latón | sin limitar tipo | latón |
| complemento de latón | sin limitar tipo | latón |
| niple | MACHÓN | — |
| accesorio niple de latón 1/2 | MACHÓN | latón y 1/2 |

«Cocina» es texto adicional, salvo que se configure como tipo, sinónimo o material. No se deducen categorías a partir de esa palabra. «Niiple» no se corrige automáticamente: debe configurarse esa variante si se quiere reconocerla.

La búsqueda reconoce nombres de tipo y sinónimos, normaliza mayúsculas, tildes y medidas, prioriza expresiones largas y conserva todas las palabras/medidas restantes. Dos tipos distintos producen una petición de concretar la búsqueda (422); no se mezclan sus artículos. Una clasificación reconocida sin artículos asociados devuelve cero resultados, sin ampliar silenciosamente a otros tipos.

Los materiales equivalentes son alternativas textuales: Inoxidable → inox, acero inoxidable. Todos los demás términos deben cumplirse además. La selección de tipo es un filtro estricto junto con categorías visibles, marcas activas y filtros del catálogo. Se aplica tanto a resultados como a sugerencias, conteo y paginación.

Las palabras generales heredadas siguen disponibles en una lista independiente. Su interruptor solo activa/desactiva la omisión de esas palabras: el comportamiento de un tipo marcado General depende de su ficha y siempre sigue la regla acordada. Un tipo específico o su sinónimo tiene prioridad sobre una palabra de esa lista.

## Persistencia y compatibilidad

`product_type_name_synonyms.is_general` comparte el carácter general/específico entre todas las familias del mismo nombre de tipo. `bootstrap` añade la columna BOOLEAN nullable de forma idempotente en PostgreSQL. NULL conserva la clasificación inicial derivada de las palabras generales existentes; al guardar una ficha se fija el valor elegido. No se borra ningún sinónimo previo ni se escribe en EXIT.

La columna opcional `General` se añade al final del Excel: Sí/No. Los archivos antiguos y peticiones antiguas sin ese campo conservan el valor actual. Se mantiene la validación completa antes de guardar y el control de versiones para evitar sobrescribir cambios de otra sesión. Los sinónimos continúan limitados a diez por nombre de tipo.

Las equivalencias de materiales se guardan en `search_settings.config.material_groups`; se derivan inicialmente de la lista anterior, reuniendo inox/inoxidable si ambos existían. Se conservan los campos de compatibilidad de la API anterior. Un cliente antiguo que actualice únicamente la lista de materiales sustituye los grupos por los derivados de esa lista.

GET `/api/v1/store/product-type-synonyms/preview?q=...` interpreta la configuración guardada sin consultar EXIT ni modificar datos. Catálogo y probador usan la misma función de interpretación. Solo operadores autorizados a Parámetros pueden configurar o probar estas reglas.

## Validación

Pruebas sobre ejemplos acordados, sinónimos generales, medidas, frases largas, equivalencias de materiales, ambigüedades, clasificación estricta sin artículos, SQL con filtros de visibilidad/paginación, compatibilidad Excel/API y persistencia de General. Pruebas React sobre la ficha, navegación conservando edición y probador. Pendiente contrastar con el catálogo real de EXIT tras integrar en desarrollo.
