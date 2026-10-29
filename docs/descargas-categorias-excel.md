# Descargas de categorías en Excel

La web descarga archivos `.xlsx` en Carga de categorías y en el enlace de clasificación de Categorías e imágenes.

| Descarga | Endpoint | Archivo |
| --- | --- | --- |
| Clasificación completa | `/api/v1/store/catalog-categories/export.xlsx` | `clasificacion_articulos.xlsx` |
| Plantilla | `/api/v1/store/catalog-categories/template.xlsx` | `plantilla_carga_categorias.xlsx` |
| Sin clasificar | `/api/v1/store/catalog-categories/missing.xlsx` | `articulos_sin_clasificacion.xlsx` |
| Preparar fotografías | `/api/v1/store/catalog-images/missing.xlsx` | `imagenes_pendientes.xlsx` |

Todos requieren sesión de operador o administrador. Los libros conservan los códigos y referencias como texto, incluidos ceros iniciales, y no interpretan valores del catálogo como fórmulas. Incorporan filtros, primera fila fija y ancho de columnas.

La clasificación completa mantiene el maestro completo de EXIT, incluidos inactivos y artículos sin stock, enriquecido con los datos de PostgreSQL. Si EXIT no responde, devuelve un error sin ofrecer una clasificación parcial. Los listados pendientes conservan sus criterios actuales. La plantilla y el listado sin clasificar usan la hoja CargaCategorias, compatible con la carga existente.

Los endpoints CSV anteriores y `/template` siguen disponibles por compatibilidad; los botones web utilizan XLSX. No cambia el cálculo de reposición, la selección de artículos ni los formatos admitidos al importar.

Validación local: pruebas de libros reales, códigos, texto literal, permisos, catálogo completo, fallo de EXIT, plantilla y listado de clasificación compatibles con el lector existente. La consulta real a EXIT se debe validar tras desplegar en desarrollo.
