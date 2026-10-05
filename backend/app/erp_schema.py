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
        "price_list": ("TarifaPrecio", "CodigoTarifa", "Tarifa", "TipoPrecio"),
        "discount_pct": ("%Descuento", "Descuento", "DescuentoComercial", "Descuento1"),
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
    # EXIT installations are not completely uniform.  Catalog queries resolve
    # the first existing candidate instead of assuming every optional column is
    # present.  ``code`` is the only required field.
    "columns": {
        "code": ("CodigoArticulo",),
        "description": ("DescripcionArticulo", "Descripcion", "Articulo"),
        "unit": ("UnidadMedidaVentas", "UnidadMedida", "UnidadVenta"),
        "manufacturer_reference": (
            "ReferenciaFabricante", "ReferenciaProveedor", "CodigoAlternativo",
        ),
        "brand_code": ("CodigoMarca", "Marca"),
        "brand_name": ("DescripcionMarca", "MarcaDescripcion", "Marca"),
        "ean": ("Ean13B2C", "EAN13", "CodigoBarras"),
        "price_with_tax": ("PrecioVentaConIVA0", "PrecioVentaconIVA0"),
        "price_without_tax": ("PrecioVentaSinIVA0", "PrecioVentasinIVA0"),
        "inactive": ("Inactivo",),
        "internet": ("Internet",),
        "web": ("ArticuloWEB",),
        "b2b": ("InternetB2B",),
        "kardex": ("EX_ArticuloKARDEX",),
    },
}

CUSTOMER_PURCHASES = {
    "schema": "dbo",
    "view": "VIS_PBI_PANELVENTAS",
    "customer_code": "CodigoCliente",
    "article_code": "CodigoArticulo",
    "units": "Unidades",
}

# Pedidos pendientes para la bandeja de operación. Los nombres de campos
# alternativos se resuelven contra INFORMATION_SCHEMA en cada instalación.
EXIT_SALES_ORDER = {
    "schema": "dbo",
    "header_table": "PedidoVentaCabecera",
    "detail_table": "PedidoVentaLineas",
}

SALES_DOCUMENTS = {
    "schema": "dbo",
    "delivery_header": "AlbaranVentaCabecera",
    "delivery_lines": "AlbaranVentaLineas",
    "invoice_header": "FacturaVenta",
    "invoice_tax": "FacturaVentaIva",
    "delivery_files": "GesDocAlbaranes",
    "invoice_files": "GesDocFacturas",
}
