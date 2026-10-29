# Categorías activas en catálogo y reposición

La configuración **Categorías e imágenes → Visible** delimita los materiales publicados en el catálogo y los incluidos en nuevos cálculos de reposición. Se reutiliza `CatalogAreaVisibility`; no hay un segundo estado independiente para reposición ni se modifican tablas de EXIT.

Una categoría oculta excluye sus materiales y sus familias, subfamilias y tipos de los selectores de reposición. «Todas» incluye únicamente las categorías permitidas. Los filtros por familia/subfamilia/tipo y los códigos manuales se cruzan con la misma regla: no permiten recuperar un material de una categoría oculta.

El catálogo aplica el filtro al listado, las búsquedas, las sugerencias, los favoritos y el detalle directo por identificador. Este último responde 404 si la categoría está oculta. Al volver a activar la categoría se recupera su consulta.

## Artículos sin categoría

Se conserva la opción existente «Artículos sin categoría»:

- Desactivada: se excluyen materiales sin clasificación local, de áreas sin clasificar y códigos desconocidos en PostgreSQL.
- Activada: se admiten esos materiales y códigos desconocidos de EXIT. Las categorías conocidas que estén ocultas siguen excluidas; activar «sin categoría» no las vuelve a incluir.

En la reposición, elegir expresamente «Artículos sin categoría» incluye los materiales con categoría nula y los grupos equivalentes sin clasificar, respetando la configuración.

## Extracción y cálculos por bloques

La selección se aplica al crear la lista de trabajo, antes de consultar el histórico de ventas y el stock. Los artículos excluidos no consumen el límite del cálculo ni aparecen en su progreso o resultados. Después se conserva el procesamiento en bloques de 1.000 artículos, con sus delegaciones juntas.

Cuando la lista de SKU ya identifica los materiales permitidos, se envía esa lista a EXIT. Si «sin categoría» está activada y corresponde consultar toda la maestra, se añade una exclusión parametrizada mediante tabla temporal de códigos de categorías ocultas, antes del límite SQL. Las cargas de códigos utilizan bloques de 1.000; no se concatenan códigos en las consultas.

La selección del trabajo queda fijada al inicializarlo. Los cambios de visibilidad se aplican al siguiente cálculo; para actualizar un resultado anterior hay que volver a calcular. Los resultados guardados y los bloques de un trabajo en curso mantienen su selección original.

## Validación

Pruebas con categorías activas/ocultas y jerarquía completa; listado, búsquedas, sugerencias, favoritos y detalle; códigos manuales y filtro directo de familia oculta; opción sin categoría en ambos estados; consultas parametrizadas antes del límite SQL; trabajo en segundo plano con verificación de artículos leídos, progreso y resultados. Pendiente comprobar el alcance y los tiempos con EXIT real en desarrollo.
