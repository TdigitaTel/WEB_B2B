import pymssql
import re

from .config import settings
from .erp_schema import ARTICLE, CUSTOMER, IMAGE, SALES_DOCUMENTS, STOCK, WAREHOUSE


def connect_sqlserver():
    """Abre una conexión al ERP SQL Server usando únicamente variables privadas."""
    missing = [
        name for name, value in {
            "SQLSERVER_HOST": settings.sqlserver_host,
            "SQLSERVER_DATABASE": settings.sqlserver_database,
            "SQLSERVER_USER": settings.sqlserver_user,
            "SQLSERVER_PASSWORD": settings.sqlserver_password,
        }.items() if not value
    ]
    if missing:
        raise RuntimeError(f"Faltan variables de SQL Server: {', '.join(missing)}")
    return pymssql.connect(
        server=settings.sqlserver_host,
        port=settings.sqlserver_port,
        user=settings.sqlserver_user,
        password=settings.sqlserver_password,
        database=settings.sqlserver_database,
        login_timeout=10,
        timeout=30,
        as_dict=True,
    )


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise RuntimeError(f"Identificador SQL Server no válido: {value}")
    return f"[{value}]"


def _discovered_column(value: str) -> str:
    """Escapa una columna cuyo nombre se obtuvo de INFORMATION_SCHEMA."""
    return f"[{value.replace(']', ']]')}]"


def _customer_columns(connection) -> dict[str, str | None]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
            (CUSTOMER["schema"], CUSTOMER["table"]),
        )
        existing = {str(row["COLUMN_NAME"]).lower(): str(row["COLUMN_NAME"]) for row in cursor.fetchall()}
    resolved: dict[str, str | None] = {}
    for field, candidates in CUSTOMER["columns"].items():
        resolved[field] = next((existing[name.lower()] for name in candidates if name.lower() in existing), None)
    if not resolved["code"]:
        raise RuntimeError("No se encontró la columna de código en dbo.clientes")
    return resolved


def fetch_customer(customer_code: str) -> dict | None:
    """Lee los datos maestros del cliente directamente de EXITERP."""
    schema = _identifier(CUSTOMER["schema"])
    table = _identifier(CUSTOMER["table"])
    with connect_sqlserver() as connection:
        columns = _customer_columns(connection)
        selections = []
        for field, column in columns.items():
            selections.append(f"c.{_discovered_column(column)} AS [{field}]" if column else f"NULL AS [{field}]")
        code_column = _discovered_column(columns["code"])
        sql = (
            f"SELECT TOP 1 {', '.join(selections)} FROM {schema}.{table} c "
            f"WHERE LTRIM(RTRIM(CONVERT(varchar(100), c.{code_column}))) = %s"
        )
        with connection.cursor() as cursor:
            cursor.execute(sql, (str(customer_code).strip(),))
            row = cursor.fetchone()
    if not row:
        return None
    return {
        "erp_id": str(row.get("code") or "").strip(),
        "legal_name": str(row.get("legal_name") or "").strip(),
        "trade_name": str(row.get("trade_name") or row.get("legal_name") or "").strip(),
        "tax_id": str(row.get("tax_id") or "").strip(),
        "email": str(row.get("email") or "").strip(),
        "phone": str(row.get("phone") or "").strip(),
        "billing_address": str(row.get("billing_address") or "").strip(),
        "price_list": str(row.get("price_list") or "").strip(),
        "discount_pct": float(row.get("discount_pct") or 0),
    }


def fetch_customer_codes(after_code: str = "", limit: int = 30) -> list[str]:
    """Devuelve una página de códigos EXIT, sin cargar la maestra completa."""
    schema = _identifier(CUSTOMER["schema"])
    table = _identifier(CUSTOMER["table"])
    with connect_sqlserver() as connection:
        columns = _customer_columns(connection)
        code_column = _discovered_column(columns["code"])
        page_size = max(1, min(int(limit), 500))
        sql = (
            f"SELECT DISTINCT TOP {page_size} "
            f"LTRIM(RTRIM(CONVERT(varchar(100), {code_column}))) AS customer_code "
            f"FROM {schema}.{table} WHERE {code_column} IS NOT NULL "
            f"AND LTRIM(RTRIM(CONVERT(varchar(100), {code_column}))) <> '' "
            f"AND LTRIM(RTRIM(CONVERT(varchar(100), {code_column}))) > %s "
            "ORDER BY customer_code"
        )
        with connection.cursor() as cursor:
            cursor.execute(sql, (str(after_code).strip(),))
            rows = cursor.fetchall()
    return [str(row["customer_code"]).strip() for row in rows if row.get("customer_code")]


def _document_id(year, series, number) -> str:
    return f"{str(year).strip()}~{str(series).strip()}~{str(number).strip()}"


def fetch_customer_delivery_notes(customer_code: str, limit: int = 200) -> list[dict]:
    """Consulta albaranes de venta directamente en EXITERP."""
    schema = _identifier(SALES_DOCUMENTS["schema"])
    table = _identifier(SALES_DOCUMENTS["delivery_header"])
    sql = (
        f"SELECT TOP {max(1, min(limit, 1000))} EjercicioAlbaran, SerieAlbaran, NumeroAlbaran, "
        "FechaAlbaran, CodigoCliente, IdDelegacion, BaseImponible, TotalCuotaIva AS TaxTotal, ImporteFactura, "
        "StatusFacturado, StatusImpresion, EjercicioPedido, SeriePedido, NumeroPedido, "
        f"EjercicioFactura, SerieFactura, NumeroFactura FROM {schema}.{table} "
        "WHERE LTRIM(RTRIM(CONVERT(varchar(100), CodigoCliente)))=%s "
        "ORDER BY FechaAlbaran DESC, EjercicioAlbaran DESC, SerieAlbaran DESC, NumeroAlbaran DESC"
    )
    with connect_sqlserver() as connection, connection.cursor() as cursor:
        cursor.execute(sql, (str(customer_code).strip(),))
        rows = cursor.fetchall()
        lines_table = _identifier(SALES_DOCUMENTS["delivery_lines"])
        line_sql = (
            f"WITH selected AS (SELECT TOP {max(1, min(limit, 1000))} CodigoEmpresa, EjercicioAlbaran, "
            f"SerieAlbaran, NumeroAlbaran, FechaAlbaran FROM {schema}.{table} "
            "WHERE LTRIM(RTRIM(CONVERT(varchar(100), CodigoCliente)))=%s "
            "ORDER BY FechaAlbaran DESC, EjercicioAlbaran DESC, SerieAlbaran DESC, NumeroAlbaran DESC) "
            "SELECT l.EjercicioAlbaran, l.SerieAlbaran, l.NumeroAlbaran, l.Orden, l.CodigoArticulo, "
            "l.DescripcionArticulo, l.Descripcion2Articulo, l.UnidadMedida1_, l.Unidades, l.Precio, "
            "l.[%Descuento] AS Descuento, l.ImporteNeto, l.BaseImponible, l.[%Iva] AS Iva, "
            "l.CuotaIva, l.ImporteLiquido, l.CodigoAlmacen "
            f"FROM {schema}.{lines_table} l INNER JOIN selected s ON s.CodigoEmpresa=l.CodigoEmpresa "
            "AND s.EjercicioAlbaran=l.EjercicioAlbaran AND s.SerieAlbaran=l.SerieAlbaran "
            "AND s.NumeroAlbaran=l.NumeroAlbaran ORDER BY l.EjercicioAlbaran DESC, l.SerieAlbaran, "
            "l.NumeroAlbaran DESC, l.Orden"
        )
        cursor.execute(line_sql, (str(customer_code).strip(),))
        line_rows = cursor.fetchall()
    lines_by_document: dict[str, list[dict]] = {}
    for line in line_rows:
        key = _document_id(line["EjercicioAlbaran"], line["SerieAlbaran"], line["NumeroAlbaran"])
        lines_by_document.setdefault(key, []).append({
            "line": int(line.get("Orden") or 0), "sku": str(line.get("CodigoArticulo") or "").strip(),
            "description": " ".join(part for part in (str(line.get("DescripcionArticulo") or "").strip(), str(line.get("Descripcion2Articulo") or "").strip()) if part),
            "unit": str(line.get("UnidadMedida1_") or "UD").strip(), "quantity": float(line.get("Unidades") or 0),
            "unit_price": float(line.get("Precio") or 0), "discount_pct": float(line.get("Descuento") or 0),
            "net_amount": float(line.get("ImporteNeto") or line.get("BaseImponible") or 0),
            "tax_rate": float(line.get("Iva") or 0), "tax_amount": float(line.get("CuotaIva") or 0),
            "total": float(line.get("ImporteLiquido") or 0), "warehouse": str(line.get("CodigoAlmacen") or "").strip(),
        })
    return [{
        "id": _document_id(row["EjercicioAlbaran"], row["SerieAlbaran"], row["NumeroAlbaran"]),
        "number": f'{row["EjercicioAlbaran"]}-{str(row["SerieAlbaran"]).strip()}-{row["NumeroAlbaran"]}',
        "created_at": row["FechaAlbaran"],
        "subtotal": float(row.get("BaseImponible") or 0),
        "tax_total": float(row.get("TaxTotal") or 0),
        "total": float(row.get("ImporteFactura") or 0),
        "status": ("FACTURADO" if int(row.get("StatusFacturado") or 0) else
                   "ENTREGADO" if int(row.get("StatusImpresion") or 0) > 0 else "PENDIENTE_DE_ENTREGA"),
        "store_code": str(row.get("IdDelegacion") or "").strip(),
        "order_number": _document_id(row.get("EjercicioPedido"), row.get("SeriePedido"), row.get("NumeroPedido")),
        "invoice_number": (_document_id(row.get("EjercicioFactura"), row.get("SerieFactura"), row.get("NumeroFactura"))
                           if int(row.get("NumeroFactura") or 0) else None),
        "source": "EXIT",
        "items": lines_by_document.get(_document_id(row["EjercicioAlbaran"], row["SerieAlbaran"], row["NumeroAlbaran"]), []),
    } for row in rows]


def fetch_customer_delivery_statuses(customer_code: str, limit: int = 1000) -> list[dict]:
    """Devuelve el vínculo pedido-albarán sin cargar las líneas del documento."""
    schema = _identifier(SALES_DOCUMENTS["schema"])
    table = _identifier(SALES_DOCUMENTS["delivery_header"])
    sql = (
        f"SELECT TOP {max(1, min(limit, 5000))} EjercicioAlbaran, SerieAlbaran, NumeroAlbaran, "
        "FechaAlbaran, FechaEntrega, FechaFirma, FechaModificacion, FechaUltimaModificacion, FechaGrabacion, "
        "StatusImpresion, StatusFacturado, FechaFactura, EjercicioPedido, SeriePedido, NumeroPedido "
        f"FROM {schema}.{table} "
        "WHERE LTRIM(RTRIM(CONVERT(varchar(100), CodigoCliente)))=%s "
        "AND COALESCE(NumeroPedido, 0) <> 0 "
        "ORDER BY FechaAlbaran DESC, EjercicioAlbaran DESC, SerieAlbaran DESC, NumeroAlbaran DESC"
    )
    with connect_sqlserver() as connection, connection.cursor() as cursor:
        cursor.execute(sql, (str(customer_code).strip(),))
        rows = cursor.fetchall()
    return [{
        "order_number": _document_id(row.get("EjercicioPedido"), row.get("SeriePedido"), row.get("NumeroPedido")),
        "delivery_number": _document_id(row.get("EjercicioAlbaran"), row.get("SerieAlbaran"), row.get("NumeroAlbaran")),
        "attended_at": row.get("FechaAlbaran"),
        # EXIT no expone FechaImpresion. FechaEntrega es la preferida y las fechas
        # de firma/modificación son la aproximación auditable cuando StatusImpresion > 0.
        "delivered_at": (row.get("FechaEntrega") or row.get("FechaFirma") or row.get("FechaModificacion")
                         or row.get("FechaUltimaModificacion") or row.get("FechaGrabacion") or row.get("FechaAlbaran")),
        "invoiced_at": row.get("FechaFactura"),
        "is_printed": int(row.get("StatusImpresion") or 0) > 0,
        "is_invoiced": int(row.get("StatusFacturado") or 0) > 0,
    } for row in rows]


def fetch_delivery_statuses_for_orders(order_numbers: list[str]) -> list[dict]:
    """Consulta en bloque los albaranes asociados a una lista de pedidos EXIT."""
    keys = []
    for value in order_numbers[:1000]:
        parts = str(value).replace("~", "/").split("/")
        if len(parts) == 3:
            keys.append(tuple(part.strip() for part in parts))
    if not keys:
        return []
    schema = _identifier(SALES_DOCUMENTS["schema"])
    table = _identifier(SALES_DOCUMENTS["delivery_header"])
    conditions, parameters = [], []
    for year, series, number in keys:
        conditions.append("(CONVERT(varchar(20),EjercicioPedido)=%s AND LTRIM(RTRIM(SeriePedido))=%s AND CONVERT(varchar(30),NumeroPedido)=%s)")
        parameters.extend((year, series, number))
    sql = (
        "SELECT EjercicioAlbaran, SerieAlbaran, NumeroAlbaran, FechaAlbaran, FechaEntrega, FechaFirma, "
        "FechaModificacion, FechaUltimaModificacion, FechaGrabacion, StatusImpresion, StatusFacturado, "
        f"FechaFactura, EjercicioPedido, SeriePedido, NumeroPedido FROM {schema}.{table} WHERE "
        + " OR ".join(conditions) +
        " ORDER BY FechaAlbaran DESC, EjercicioAlbaran DESC, SerieAlbaran DESC, NumeroAlbaran DESC"
    )
    with connect_sqlserver() as connection, connection.cursor() as cursor:
        cursor.execute(sql, tuple(parameters))
        rows = cursor.fetchall()
    return [{
        "order_number": _document_id(row.get("EjercicioPedido"), row.get("SeriePedido"), row.get("NumeroPedido")),
        "delivery_number": _document_id(row.get("EjercicioAlbaran"), row.get("SerieAlbaran"), row.get("NumeroAlbaran")),
        "attended_at": row.get("FechaAlbaran"),
        "delivered_at": (row.get("FechaEntrega") or row.get("FechaFirma") or row.get("FechaModificacion")
                         or row.get("FechaUltimaModificacion") or row.get("FechaGrabacion") or row.get("FechaAlbaran")),
        "invoiced_at": row.get("FechaFactura"),
        "is_printed": int(row.get("StatusImpresion") or 0) > 0,
        "is_invoiced": int(row.get("StatusFacturado") or 0) > 0,
    } for row in rows]


def fetch_customer_invoices(customer_code: str, limit: int = 200) -> list[dict]:
    """Consulta facturas de venta directamente en EXITERP."""
    schema = _identifier(SALES_DOCUMENTS["schema"])
    table = _identifier(SALES_DOCUMENTS["invoice_header"])
    tax_table = _identifier(SALES_DOCUMENTS["invoice_tax"])
    due_dates = ", ".join(f"i.FechaVencimiento{index}" for index in range(1, 13))
    sql = (
        f"SELECT TOP {max(1, min(limit, 1000))} f.EjercicioFactura, f.SerieFactura, f.NumeroFactura, "
        "f.FechaFactura, f.FechaRegistro, f.CodigoCliente, f.IdDelegacion, f.BaseImponible, "
        "f.TotalCuotaIva AS TaxTotal, f.ImporteFactura, f.StatusCartera, f.Documento, "
        f"COALESCE({due_dates}) AS FechaVencimiento FROM {schema}.{table} f "
        f"LEFT JOIN {schema}.{tax_table} i ON i.CodigoEmpresa=f.CodigoEmpresa "
        "AND i.EjercicioFactura=f.EjercicioFactura AND i.SerieFactura=f.SerieFactura "
        "AND i.NumeroFactura=f.NumeroFactura "
        "WHERE LTRIM(RTRIM(CONVERT(varchar(100), f.CodigoCliente)))=%s "
        "ORDER BY f.FechaFactura DESC, f.EjercicioFactura DESC, f.SerieFactura DESC, f.NumeroFactura DESC"
    )
    with connect_sqlserver() as connection, connection.cursor() as cursor:
        cursor.execute(sql, (str(customer_code).strip(),))
        rows = cursor.fetchall()
    return [{
        "id": _document_id(row["EjercicioFactura"], row["SerieFactura"], row["NumeroFactura"]),
        "number": f'{row["EjercicioFactura"]}-{str(row["SerieFactura"]).strip()}-{row["NumeroFactura"]}',
        "created_at": row.get("FechaFactura") or row.get("FechaRegistro"),
        "due_date": row.get("FechaVencimiento"),
        "subtotal": float(row.get("BaseImponible") or 0),
        "tax_total": float(row.get("TaxTotal") or 0),
        "total": float(row.get("ImporteFactura") or 0),
        "status": str(row.get("StatusCartera") or "REGISTRADA"),
        "store_code": str(row.get("IdDelegacion") or "").strip(),
        "document": str(row.get("Documento") or "").strip() or None,
        "source": "EXIT",
    } for row in rows]


def fetch_product_image(article_code: str) -> bytes | None:
    schema = _identifier(IMAGE["schema"])
    table = _identifier(IMAGE["table"])
    key_column = _identifier(IMAGE["article_code"])
    image_column = _identifier(IMAGE["data"])
    sql = (
        f"SELECT TOP 1 {image_column} AS image_data "
        f"FROM {schema}.{table} "
        f"WHERE {key_column} = %s AND {image_column} IS NOT NULL"
    )
    with connect_sqlserver() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, (article_code,))
            row = cursor.fetchone()
    if not row or row["image_data"] is None:
        return None
    return normalize_image_data(bytes(row["image_data"]))


def fetch_product_images(article_codes: list[str]) -> dict[str, bytes]:
    codes = list(dict.fromkeys(str(code).strip() for code in article_codes if str(code).strip()))
    if not codes:
        return {}
    schema = _identifier(IMAGE["schema"])
    table = _identifier(IMAGE["table"])
    key_column = _identifier(IMAGE["article_code"])
    image_column = _identifier(IMAGE["data"])
    placeholders = ", ".join(["%s"] * len(codes))
    sql = (
        f"SELECT LTRIM(RTRIM(CONVERT(varchar(100), {key_column}))) AS article_code, "
        f"{image_column} AS image_data FROM {schema}.{table} "
        f"WHERE LTRIM(RTRIM(CONVERT(varchar(100), {key_column}))) IN ({placeholders}) "
        f"AND {image_column} IS NOT NULL"
    )
    with connect_sqlserver() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, tuple(codes))
            rows = cursor.fetchall()
    return {
        str(row["article_code"]).strip(): normalize_image_data(bytes(row["image_data"]))
        for row in rows if row["image_data"]
    }


def fetch_product_stocks(article_codes: list[str]) -> dict[str, list[dict]]:
    """Obtiene el stock ERP agrupado por articulo y almacen en una sola consulta."""
    codes = list(dict.fromkeys(str(code).strip() for code in article_codes if str(code).strip()))
    if not codes:
        return {}

    stock_schema = _identifier(STOCK["schema"])
    stock_table = _identifier(STOCK["table"])
    article_column = _identifier(STOCK["article_code"])
    warehouse_column = _identifier(STOCK["warehouse_code"])
    units_column = _identifier(STOCK["units"])
    warehouses_schema = _identifier(WAREHOUSE["schema"])
    warehouses_table = _identifier(WAREHOUSE["table"])
    warehouses_code_column = _identifier(WAREHOUSE["code"])
    description_column = _identifier(WAREHOUSE["name"])
    excluded = [code.strip() for code in settings.sqlserver_stock_excluded_warehouses.split(",") if code.strip()]

    code_placeholders = ", ".join(["%s"] * len(codes))
    exclusion_sql = ""
    parameters = list(codes)
    if excluded:
        exclusion_sql = f"AND LTRIM(RTRIM(CONVERT(varchar(100), s.{warehouse_column}))) NOT IN ({', '.join(['%s'] * len(excluded))}) "
        parameters.extend(excluded)

    sql = (
        f"SELECT LTRIM(RTRIM(CONVERT(varchar(100), s.{article_column}))) AS article_code, "
        f"LTRIM(RTRIM(CONVERT(varchar(100), s.{warehouse_column}))) AS warehouse_code, "
        f"COALESCE(CONVERT(varchar(250), a.{description_column}), "
        f"LTRIM(RTRIM(CONVERT(varchar(100), s.{warehouse_column})))) AS warehouse_name, "
        f"SUM(COALESCE(s.{units_column}, 0)) AS available "
        f"FROM {stock_schema}.{stock_table} s "
        f"LEFT JOIN {warehouses_schema}.{warehouses_table} a "
        f"ON LTRIM(RTRIM(CONVERT(varchar(100), a.{warehouses_code_column}))) = "
        f"LTRIM(RTRIM(CONVERT(varchar(100), s.{warehouse_column}))) "
        f"WHERE LTRIM(RTRIM(CONVERT(varchar(100), s.{article_column}))) IN ({code_placeholders}) "
        f"{exclusion_sql}"
        f"GROUP BY s.{article_column}, s.{warehouse_column}, a.{description_column} "
        f"ORDER BY article_code, warehouse_name"
    )
    with connect_sqlserver() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, tuple(parameters))
            rows = cursor.fetchall()

    result: dict[str, list[dict]] = {code: [] for code in codes}
    combined_00_99: dict[str, float] = {}
    for row in rows:
        code = str(row["article_code"]).strip()
        warehouse_code = str(row["warehouse_code"]).strip()
        available = float(row["available"] or 0)
        if warehouse_code in {"00", "99"}:
            combined_00_99[code] = combined_00_99.get(code, 0) + available
            continue
        result.setdefault(code, []).append({
            "store_code": warehouse_code,
            "store": str(row["warehouse_name"]).strip(),
            "available": available,
        })
    for code, available in combined_00_99.items():
        result.setdefault(code, []).append({
            "store_code": "00",
            "store": "Almeiras",
            "available": available,
        })
    for stock in result.values():
        stock.sort(key=lambda item: item["store"])
    return result


def fetch_product_stock(article_code: str) -> list[dict]:
    return fetch_product_stocks([article_code]).get(str(article_code).strip(), [])


def fetch_product_prices(article_codes: list[str]) -> dict[str, dict]:
    """Obtiene los precios con y sin IVA de la tabla de articulos del ERP."""
    codes = list(dict.fromkeys(str(code).strip() for code in article_codes if str(code).strip()))
    if not codes:
        return {}
    schema = _identifier(ARTICLE["schema"])
    table = _identifier(ARTICLE["table"])
    code_column = _identifier(ARTICLE["code"])
    with_tax_column = _identifier(ARTICLE["price_with_tax"])
    without_tax_column = _identifier(ARTICLE["price_without_tax"])
    placeholders = ", ".join(["%s"] * len(codes))
    sql = (
        f"SELECT LTRIM(RTRIM(CONVERT(varchar(100), {code_column}))) AS article_code, "
        f"COALESCE({with_tax_column}, 0) AS price_with_tax, "
        f"COALESCE({without_tax_column}, 0) AS price_without_tax "
        f"FROM {schema}.{table} "
        f"WHERE LTRIM(RTRIM(CONVERT(varchar(100), {code_column}))) IN ({placeholders})"
    )
    with connect_sqlserver() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, tuple(codes))
            rows = cursor.fetchall()
    return {
        str(row["article_code"]).strip(): {
            "with_tax": float(row["price_with_tax"] or 0),
            "without_tax": float(row["price_without_tax"] or 0),
        }
        for row in rows
    }


def fetch_product_price(article_code: str) -> dict | None:
    return fetch_product_prices([article_code]).get(str(article_code).strip())


def normalize_image_data(data: bytes) -> bytes:
    """Elimina cabeceras OLE/propietarias anteriores al contenido gráfico real."""
    signatures = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a", b"BM", b"RIFF")
    positions = [position for signature in signatures if (position := data.find(signature, 0, 8192)) >= 0]
    if positions:
        return data[min(positions):]
    return data


def image_media_type(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"BM"):
        return "image/bmp"
    if data.startswith((b"RIFF",)) and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"
