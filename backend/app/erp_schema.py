"""Mapa interno del esquema EXITERP usado por la integración B2B."""

IMAGE = {
    "schema": "dbo",
    "table": "imagenes",
    "article_code": "CodigoArticulo",
    "data": "imagen",
}

STOCK = {
    "schema": "dbo",
    "table": "tempstockarticulo",
    "article_code": "CodigoArticulo",
    "warehouse_code": "CodigoAlmacen",
    "units": "UnidadesSaldo",
}

WAREHOUSE = {
    "schema": "dbo",
    "table": "almacenes",
    "code": "CodigoAlmacen",
    "name": "Almacen",
}

ARTICLE = {
    "schema": "dbo",
    "table": "articulos",
    "code": "CodigoArticulo",
    "price_with_tax": "PrecioVentaConIVA0",
    "price_without_tax": "PrecioVentaSinIVA0",
}
