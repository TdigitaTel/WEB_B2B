# Publicación de artículos sin categoría

Los artículos sin categoría web no se publican por defecto en el catálogo, las búsquedas, sugerencias ni favoritos. El filtro se aplica en SQL Server antes del recuento y la paginación, limitando la consulta a los códigos con categoría PostgreSQL válida. EXIT continúa siendo la maestra de artículos.

Se consideran sin categoría los productos sin material_area_id, los asignados a SIN CLASIFICAR/SIN CATEGORIA/SIN CATEGORÍA y los códigos de EXIT que aún no tienen clasificación complementaria en PostgreSQL.

El operador administra esta opción en Categorías e imágenes, fila Artículos sin categoría. Su valor inicial es Oculta; se puede activar expresamente. El control utiliza las tablas de categorías y visibilidad existentes, sin migración. No se borran ni reclasifican materiales. La exportación completa de clasificación permanece disponible para trabajar los pendientes.

Validación: 128 pruebas backend, compilación Next.js y TypeScript y git diff --check correctos. Las pruebas de compra preparan artículos con categoría para representar productos publicados. Pendiente de validación funcional en desarrollo.

Los filtros y selectores del catálogo incluyen todas las categorías configuradas como visibles, aunque no tengan artículos activos o falte completar familia, subfamilia o tipo. Las categorías ocultas se excluyen. El grupo Artículos sin categoría también puede seleccionarse cuando se habilita.
