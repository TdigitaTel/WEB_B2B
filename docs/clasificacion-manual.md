# Asignación manual de materiales

Disponible para operadores con permiso de **Categorías** y administradores, en **Categorías → Asignación manual**. Se conserva la pestaña de visibilidad e imágenes y la carga por archivo existente.

1. Buscar por código, descripción, referencia de fabricante, EAN o marca. Se utiliza el mismo buscador de materiales, con sus equivalencias y sinónimos. Los filtros de origen son categoría, familia, subfamilia y tipo, además de «Solo materiales sin clasificar».
2. Marcar materiales o pulsar «Seleccionar esta página». La lista admite 50 resultados por página y conserva la selección explícita entre páginas y búsquedas. «Ver selección completa» permite revisar y quitar materiales. Máximo: 5.000 por operación; no se seleccionan resultados ocultos automáticamente.
3. Elegir la clasificación completa de destino. Se puede crear una subfamilia dentro de una familia existente y un tipo dentro de una subfamilia. Los códigos se generan automáticamente. Un nombre repetido dentro del mismo padre selecciona el existente.
4. Revisar el número seleccionado y la ruta de destino y confirmar. Tras un error se mantiene la selección para corregir o reintentar.

La búsqueda administrativa incluye la maestra EXIT aunque haya materiales inactivos, marcas/categorías no visibles o artículos sin stock. Esta ampliación es exclusiva de la herramienta: el catálogo comercial conserva sus reglas de visibilidad y stock.

La asignación modifica la jerarquía web en PostgreSQL, derivando los cuatro niveles desde el tipo de destino. Conserva IDs, nombres homologados, marcas, precios, unidades, atributos, imágenes y estado de activación de fichas existentes. Los artículos que existen en EXIT y no tienen ficha web reciben una ficha local. No se escriben datos comerciales en EXIT ni se modifican líneas de pedidos.

La operación es una transacción completa: se verifica primero que todos los códigos seleccionados existan en EXIT. Si falta uno o falla una restricción de la base, no se aplica parte del lote. Queda un registro de la clasificación anterior y el destino en `material_import_rows` con origen `MANUAL`, y un evento de auditoría por lote. No requiere tablas nuevas ni una migración manual.

API, bajo el permiso existente `categories`:

- `GET /api/v1/store/catalog-categories/manual/tree`
- `GET /api/v1/store/catalog-categories/manual/materials`
- `POST /api/v1/store/catalog-categories/manual/assign`
- `POST /api/v1/store/catalog-categories/manual/subfamilies`
- `POST /api/v1/store/catalog-categories/manual/product-types`

Las pruebas utilizan una base desechable, respuestas EXIT simuladas y comprobaciones de permisos, datos conservados, rollback y selección en varias páginas. No se han ejecutado asignaciones en desarrollo ni producción desde esta tarea.
