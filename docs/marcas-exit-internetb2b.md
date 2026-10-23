# Marcas de EXIT y publicación del catálogo

El operador dispone del visor Parámetros → Marcas de EXIT, con código, descripción, empresa cuando existe, InternetB2B y estado de publicación. Permite buscar, filtrar permitidas/excluidas y paginar de 50 en 50. Es de solo lectura: los cambios se realizan en EXIT y Actualizar desde EXIT vuelve a consultar los valores.

La consulta del catálogo incorpora NOT EXISTS contra dbo.marcas: excluye el artículo cuando su Marca (alternativa CodigoMarca) coincide con una marca cuyo InternetB2B = -1. Un valor 0 no lo excluye. Si ambos maestros tienen CodigoEmpresa, forma parte del vínculo. Las marcas sin coincidencia y las nulas no se excluyen por este criterio; siguen aplicando actividad, categorías y demás filtros.

El criterio se aplica en SQL Server antes del recuento y de la página. También cubre sugerencias y lecturas activas por código utilizadas por favoritos; las lecturas históricas con active_only=False no se modifican. No carga listas de códigos por marca ni altera datos de EXIT. Si faltan las columnas necesarias devuelve un error de consulta en lugar de omitir silenciosamente el filtro.

GET /api/v1/store/catalog-brands está reservado a operador y administrador. No requiere migración PostgreSQL ni permisos de escritura sobre EXIT.

Validación: pruebas de resolución de columnas, vínculo por marca/empresa, flag 0/-1, permiso del visor y aplicación antes de COUNT/OFFSET. Pendiente de comprobación funcional con el esquema real de EXIT en desarrollo.
