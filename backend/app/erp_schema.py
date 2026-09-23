"""Mapa interno del esquema EXITERP usado por la integración B2B."""

IMAGE = {
    "schema": "dbo",
    "table": "imagenes",
    "article_code": "CodigoArticulo",
    "data": "imagen",
}

STOCK = {
    "schema": "dbo",
    "table": "vis_ex_stockarticuloalmacen",
    "article_code": "CodigoArticulo",
    "warehouse_code": "CodigoAlmacen",
    "units": "UnidadSaldo",
}

CUSTOMER = {
    "schema": "dbo",
    "table": "clientes",
    # EXITERP installations can expose the same fields with slightly different
    # names. erp_db resolves the first candidate that exists in the live table.
    "columns": {
        "code": ("CodigoCliente", "Cliente", "CodCliente"),
        "legal_name": ("RazonSocial", "RazonSocial1", "NombreCliente", "Nombre"),
        "trade_name": ("NombreComercial", "RazonSocial", "NombreCliente", "Nombre"),
        "tax_id": ("CifDni", "CIFDNI", "Cif", "Nif", "CifNif"),
        "email": ("Email1", "Email", "CorreoElectronico", "Correo"),
        "phone": ("Telefono", "Telefono1", "Movil"),
        "billing_address": ("Domicilio", "Direccion", "Domicilio1"),
        "price_list": ("CodigoTarifa", "Tarifa", "TipoPrecio"),
        "discount_pct": ("Descuento", "DescuentoComercial", "Descuento1"),
    },
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
