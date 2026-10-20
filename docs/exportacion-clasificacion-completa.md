# Descarga completa de clasificación

El botón Descargar clasificación completa, disponible para operadores y administradores, cruza todos los códigos no vacíos de dbo.articulos (EXIT SQL Server) con la clasificación PostgreSQL. No aplica filtros de stock, Inactivo, situación, Internet, ArticuloWEB, InternetB2B, categoría visible ni paginación. No modifica ninguna base de datos.

También conserva artículos presentes solo en PostgreSQL. ExisteEnEXIT y ExisteEnWeb distinguen los orígenes; un código solo en EXIT muestra SIN_CLASIFICAR y las categorías vacías. La descripción principal procede de EXIT cuando existe; DescripcionWeb conserva el nombre de la web.

Activo conserva el estado de PostgreSQL. ActivoEXIT interpreta InactivoEXIT (0: Sí, 1: No); queda vacío si ese estado no existe o no es reconocible. InactivoEXIT, SituacionEXIT, InternetEXIT, ArticuloWEBEXIT e InternetB2BEXIT muestran el valor original como texto, sin inferir que 0 equivale a ausencia. Si una columna no está disponible en EXIT, queda vacía. VisibleCategoriaWeb describe la configuración de la categoría y no filtra la exportación. Se incluyen marca, referencia de fabricante y unidad de EXIT.

La consulta completa usa las credenciales SQL Server del backend. Si EXIT falla se devuelve HTTP 503, sin generar un archivo parcial basado únicamente en PostgreSQL. No requiere cambios de esquema ni migraciones. El catálogo de compra conserva sus reglas actuales.
