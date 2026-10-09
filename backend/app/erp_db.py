import pymssql
import re
from datetime import date

from .config import settings
from .erp_schema import ARTICLE, CUSTOMER, CUSTOMER_PURCHASES, IMAGE, SALES_DOCUMENTS, STOCK, WAREHOUSE
from .search import normalize_query


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


def _article_columns(connection) -> dict[str, str | None]:
    """Resuelve las columnas disponibles de la maestra de artículos EXIT."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
            (ARTICLE["schema"], ARTICLE["table"]),
        )
        existing = {str(row["COLUMN_NAME"]).lower(): str(row["COLUMN_NAME"]) for row in cursor.fetchall()}
    resolved: dict[str, str | None] = {}
    for field, candidates in ARTICLE["columns"].items():
        resolved[field] = next((existing[name.lower()] for name in candidates if name.lower() in existing), None)
    if not resolved["code"]:
        raise RuntimeError("No se encontró la columna de código en dbo.articulos")
    return resolved


def _article_text(column: str | None, alias: str = "a", length: int = 500) -> str:
    if not column:
        return "NULL"
    return f"LTRIM(RTRIM(CONVERT(varchar({length}), {alias}.{_discovered_column(column)})))"


def _article_number(column: str | None, alias: str = "a") -> str:
    if not column:
        return "0"
    return f"COALESCE({alias}.{_discovered_column(column)}, 0)"


def _article_from_row(row: dict) -> dict:
    return {
        "article_code": str(row.get("article_code") or "").strip(),
        "description": str(row.get("description") or row.get("article_code") or "").strip(),
        "unit": str(row.get("unit") or "UD").strip() or "UD",
        "manufacturer_reference": str(row.get("manufacturer_reference") or "").strip(),
        "brand_code": str(row.get("brand_code") or "").strip(),
        "brand_name": str(row.get("brand_name") or "").strip(),
        "ean": str(row.get("ean") or "").strip(),
        "price_with_tax": float(row.get("price_with_tax") or 0),
        "price_without_tax": float(row.get("price_without_tax") or 0),
    }


def _prepare_eligible_articles(cursor, article_codes: list[str] | None) -> str:
    """Carga códigos de clasificación en una tabla temporal para evitar el límite de parámetros."""
    if article_codes is None:
        return ""
    cursor.execute(
        "CREATE TABLE #EligibleArticles "
        "(article_code varchar(100) COLLATE DATABASE_DEFAULT NOT NULL PRIMARY KEY)"
    )
    codes = list(dict.fromkeys(str(code).strip() for code in article_codes if str(code).strip()))
    if codes:
        cursor.executemany("INSERT INTO #EligibleArticles (article_code) VALUES (%s)", [(code,) for code in codes])
    return "INNER JOIN #EligibleArticles e ON e.article_code = "


def fetch_catalog_articles(query: str = "", page: int = 1, page_size: int = 24,
                           article_codes: list[str] | None = None, excluded_codes: list[str] | None = None) -> tuple[list[dict], int]:
    """Pagina la maestra activa de EXIT; PostgreSQL solo limita por clasificación."""
    if article_codes is not None and not article_codes:
        return [], 0
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 100))
    schema = _identifier(ARTICLE["schema"])
    table = _identifier(ARTICLE["table"])
    with connect_sqlserver() as connection, connection.cursor() as cursor:
        columns = _article_columns(connection)
        code_expression = _article_text(columns["code"], length=100)
        description_expression = _article_text(columns["description"])
        reference_expression = _article_text(columns["manufacturer_reference"], length=200)
        ean_expression = _article_text(columns["ean"], length=100)
        brand_expression = _article_text(columns["brand_name"], length=200)
        eligible_prefix = _prepare_eligible_articles(cursor, article_codes)
        eligible_join = f"{eligible_prefix}{code_expression} " if eligible_prefix else ""
        conditions = [f"{code_expression} <> ''"]
        if excluded_codes:
            cursor.execute("CREATE TABLE #HiddenArticles (article_code nvarchar(100) PRIMARY KEY)")
            cursor.executemany("INSERT INTO #HiddenArticles (article_code) VALUES (%s)", [(code,) for code in dict.fromkeys(excluded_codes)])
            conditions.append(f"NOT EXISTS (SELECT 1 FROM #HiddenArticles hidden WHERE hidden.article_code = {code_expression})")
        parameters: list = []
        if columns["inactive"]:
            conditions.append(f"COALESCE(a.{_discovered_column(columns['inactive'])}, 0) = 0")
        normalized_query = normalize_query(query)
        stock_join = ""
        stock_parameters: list = []
        order_expression = code_expression
        if not normalized_query:
            excluded = [code.strip() for code in settings.sqlserver_stock_excluded_warehouses.split(",") if code.strip()]
            exclusion = ""
            if excluded:
                exclusion = (
                    f"WHERE LTRIM(RTRIM(CONVERT(varchar(100), s.{_identifier(STOCK['warehouse_code'])}))) "
                    f"NOT IN ({', '.join(['%s'] * len(excluded))}) "
                )
                stock_parameters.extend(excluded)
            stock_code = f"LTRIM(RTRIM(CONVERT(varchar(100), s.{_identifier(STOCK['article_code'])})))"
            stock_join = (
                f"INNER JOIN (SELECT {stock_code} AS article_code, "
                f"SUM(COALESCE(s.{_identifier(STOCK['units'])}, 0)) AS available "
                f"FROM {_identifier(STOCK['schema'])}.{_identifier(STOCK['table'])} s {exclusion}"
                f"GROUP BY {stock_code} "
                f"HAVING SUM(COALESCE(s.{_identifier(STOCK['units'])}, 0)) > 0) stock "
                f"ON stock.article_code = {code_expression} "
            )
            order_expression = f"stock.available DESC, {code_expression}"
        if normalized_query:
            searchable = [code_expression]
            searchable.extend(expression for expression in (
                description_expression, reference_expression, ean_expression, brand_expression,
            ) if expression != "NULL")
            for term in normalized_query.split():
                conditions.append("(" + " OR ".join(f"{expression} LIKE %s" for expression in searchable) + ")")
                parameters.extend([f"%{term}%"] * len(searchable))
        parameters = stock_parameters + parameters
        from_sql = f"FROM {schema}.{table} a {eligible_join}{stock_join}WHERE " + " AND ".join(conditions)
        cursor.execute(f"SELECT COUNT_BIG(*) AS total {from_sql}", tuple(parameters))
        total = int((cursor.fetchone() or {}).get("total") or 0)
        selections = {
            "article_code": code_expression,
            "description": description_expression,
            "unit": _article_text(columns["unit"], length=80),
            "manufacturer_reference": reference_expression,
            "brand_code": _article_text(columns["brand_code"], length=100),
            "brand_name": brand_expression,
            "ean": ean_expression,
            "price_with_tax": _article_number(columns["price_with_tax"]),
            "price_without_tax": _article_number(columns["price_without_tax"]),
        }
        select_sql = ", ".join(f"{expression} AS [{name}]" for name, expression in selections.items())
        page_parameters = [*parameters, (page - 1) * page_size, page_size]
        cursor.execute(
            f"SELECT {select_sql} {from_sql} ORDER BY {order_expression} "
            "OFFSET %s ROWS FETCH NEXT %s ROWS ONLY",
            tuple(page_parameters),
        )
        rows = cursor.fetchall()
    return [_article_from_row(row) for row in rows], total


def fetch_catalog_articles_by_codes(article_codes: list[str], active_only: bool = True) -> dict[str, dict]:
    """Lee en bloque los datos vivos de EXIT para códigos ya conocidos por la web."""
    codes = list(dict.fromkeys(str(code).strip() for code in article_codes if str(code).strip()))
    if not codes:
        return {}
    schema = _identifier(ARTICLE["schema"])
    table = _identifier(ARTICLE["table"])
    with connect_sqlserver() as connection, connection.cursor() as cursor:
        columns = _article_columns(connection)
        code_expression = _article_text(columns["code"], length=100)
        eligible_prefix = _prepare_eligible_articles(cursor, codes)
        eligible_join = f"{eligible_prefix}{code_expression} "
        selections = {
            "article_code": code_expression,
            "description": _article_text(columns["description"]),
            "unit": _article_text(columns["unit"], length=80),
            "manufacturer_reference": _article_text(columns["manufacturer_reference"], length=200),
            "brand_code": _article_text(columns["brand_code"], length=100),
            "brand_name": _article_text(columns["brand_name"], length=200),
            "ean": _article_text(columns["ean"], length=100),
            "price_with_tax": _article_number(columns["price_with_tax"]),
            "price_without_tax": _article_number(columns["price_without_tax"]),
        }
        conditions = [f"{code_expression} <> ''"]
        if active_only and columns["inactive"]:
            conditions.append(f"COALESCE(a.{_discovered_column(columns['inactive'])}, 0) = 0")
        select_sql = ", ".join(f"{expression} AS [{name}]" for name, expression in selections.items())
        cursor.execute(
            f"SELECT {select_sql} FROM {schema}.{table} a {eligible_join}WHERE " + " AND ".join(conditions)
        )
        rows = cursor.fetchall()
    articles = [_article_from_row(row) for row in rows]
    return {article["article_code"]: article for article in articles}


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


def fetch_customer_favorite_articles(customer_code: str, limit: int = 8) -> list[dict]:
    """Devuelve los artículos más comprados por el cliente, ordenados por unidades."""
    schema = _identifier(CUSTOMER_PURCHASES["schema"])
    view = _identifier(CUSTOMER_PURCHASES["view"])
    customer_column = _identifier(CUSTOMER_PURCHASES["customer_code"])
    article_column = _identifier(CUSTOMER_PURCHASES["article_code"])
    units_column = _identifier(CUSTOMER_PURCHASES["units"])
    result_limit = max(1, min(int(limit), 50))
    sql = (
        f"SELECT TOP {result_limit} "
        f"LTRIM(RTRIM(CONVERT(varchar(100), v.{article_column}))) AS article_code, "
        f"SUM(COALESCE(v.{units_column}, 0)) AS purchased_units "
        f"FROM {schema}.{view} v "
        f"WHERE LTRIM(RTRIM(CONVERT(varchar(100), v.{customer_column}))) = %s "
        f"AND v.{article_column} IS NOT NULL "
        f"AND LTRIM(RTRIM(CONVERT(varchar(100), v.{article_column}))) <> '' "
        f"GROUP BY v.{article_column} "
        f"ORDER BY purchased_units DESC, article_code"
    )
    with connect_sqlserver() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, (str(customer_code).strip(),))
            rows = cursor.fetchall()
    return [
        {
            "article_code": str(row["article_code"]).strip(),
            "purchased_units": float(row["purchased_units"] or 0),
        }
        for row in rows
        if row.get("article_code")
    ]


def _document_id(year, series, number) -> str:
    return f"{str(year).strip()}~{str(series).strip()}~{str(number).strip()}"


def _document_filters(alias: str, prefix: str, document_number: str = "", date_from: date | None = None,
                      date_to: date | None = None) -> tuple[str, list]:
    clauses, parameters = [], []
    if date_from:
        clauses.append(f"{alias}.Fecha{prefix} >= %s")
        parameters.append(date_from)
    if date_to:
        clauses.append(f"{alias}.Fecha{prefix} < DATEADD(day, 1, %s)")
        parameters.append(date_to)
    raw = str(document_number or "").strip()
    if raw:
        parts = [part.strip() for part in re.split(r"[~/\\-]+", raw) if part.strip()]
        if len(parts) >= 3:
            clauses.extend((
                f"CONVERT(varchar(20), {alias}.Ejercicio{prefix}) = %s",
                f"LTRIM(RTRIM(CONVERT(varchar(30), {alias}.Serie{prefix}))) = %s",
                f"CONVERT(varchar(30), {alias}.Numero{prefix}) = %s",
            ))
            parameters.extend((parts[-3], parts[-2], parts[-1]))
        else:
            clauses.append(f"CONVERT(varchar(30), {alias}.Numero{prefix}) = %s")
            parameters.append(raw)
    return ("".join(f" AND {clause}" for clause in clauses), parameters)


def fetch_customer_delivery_notes(customer_code: str, limit: int = 200, document_number: str = "",
                                  date_from: date | None = None, date_to: date | None = None) -> list[dict]:
    """Consulta albaranes de venta directamente en EXITERP."""
    schema = _identifier(SALES_DOCUMENTS["schema"])
    table = _identifier(SALES_DOCUMENTS["delivery_header"])
    filters_sql, filter_parameters = _document_filters("a", "Albaran", document_number, date_from, date_to)
    sql = (
        f"SELECT TOP {max(1, min(limit, 1000))} EjercicioAlbaran, SerieAlbaran, NumeroAlbaran, "
        "FechaAlbaran, CodigoCliente, IdDelegacion, BaseImponible, TotalCuotaIva AS TaxTotal, ImporteFactura, "
        "StatusFacturado, StatusImpresion, EjercicioPedido, SeriePedido, NumeroPedido, "
        f"EjercicioFactura, SerieFactura, NumeroFactura FROM {schema}.{table} a "
        "WHERE LTRIM(RTRIM(CONVERT(varchar(100), a.CodigoCliente)))=%s " + filters_sql + " "
        "ORDER BY FechaAlbaran DESC, EjercicioAlbaran DESC, SerieAlbaran DESC, NumeroAlbaran DESC"
    )
    with connect_sqlserver() as connection, connection.cursor() as cursor:
        parameters = [str(customer_code).strip(), *filter_parameters]
        cursor.execute(sql, tuple(parameters))
        rows = cursor.fetchall()
        lines_table = _identifier(SALES_DOCUMENTS["delivery_lines"])
        line_sql = (
            f"WITH selected AS (SELECT TOP {max(1, min(limit, 1000))} CodigoEmpresa, EjercicioAlbaran, "
            f"SerieAlbaran, NumeroAlbaran, FechaAlbaran FROM {schema}.{table} a "
            "WHERE LTRIM(RTRIM(CONVERT(varchar(100), a.CodigoCliente)))=%s " + filters_sql + " "
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
        cursor.execute(line_sql, tuple(parameters))
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
        "status": ("FACTURADO" if int(row.get("StatusFacturado") or 0) == -1 and int(row.get("NumeroFactura") or 0) > 0 else
                   "ENTREGADO" if int(row.get("StatusImpresion") or 0) == -1 else "PENDIENTE_DE_ENTREGA"),
        "store_code": str(row.get("IdDelegacion") or "").strip(),
        "order_number": _document_id(row.get("EjercicioPedido"), row.get("SeriePedido"), row.get("NumeroPedido")),
        "invoice_number": (f'{row.get("EjercicioFactura")}-{str(row.get("SerieFactura") or "").strip()}-{row.get("NumeroFactura")}'
                           if int(row.get("NumeroFactura") or 0) else None),
        "source": "EXIT",
        "items": lines_by_document.get(_document_id(row["EjercicioAlbaran"], row["SerieAlbaran"], row["NumeroAlbaran"]), []),
    } for row in rows]


def _delivery_registration_sql(connection, sql):
    with connection.cursor() as cursor:
        cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s", (SALES_DOCUMENTS["schema"], SALES_DOCUMENTS["delivery_header"]))
        columns = {row['COLUMN_NAME'].lower(): row['COLUMN_NAME'] for row in cursor.fetchall()}
    column = columns.get('horagrabacion') or columns.get('horaregistro')
    expression = _discovered_column(column) if column else 'NULL'
    return sql.replace('FechaAlbaran,', f'FechaAlbaran, {expression} AS delivery_recorded_time,', 1).replace('ORDER BY FechaAlbaran DESC,', 'ORDER BY FechaAlbaran DESC, delivery_recorded_time DESC,')


def _delivery_attended_at(row):
    from .exit_db import _exit_datetime
    return _exit_datetime(row['FechaAlbaran'], row.get('delivery_recorded_time')) if row.get('FechaAlbaran') else None


def fetch_customer_delivery_statuses(customer_code: str, limit: int = 1000) -> list[dict]:
    """Devuelve el vínculo pedido-albarán sin cargar las líneas del documento."""
    schema = _identifier(SALES_DOCUMENTS["schema"])
    table = _identifier(SALES_DOCUMENTS["delivery_header"])
    sql = (
        f"SELECT TOP {max(1, min(limit, 5000))} EjercicioAlbaran, SerieAlbaran, NumeroAlbaran, "
        "FechaAlbaran, FechaEntrega, FechaFirma, FechaModificacion, FechaUltimaModificacion, FechaGrabacion, "
        "StatusImpresion, StatusFacturado, FechaFactura, EjercicioFactura, SerieFactura, NumeroFactura, "
        "EjercicioPedido, SeriePedido, NumeroPedido "
        f"FROM {schema}.{table} "
        "WHERE LTRIM(RTRIM(CONVERT(varchar(100), CodigoCliente)))=%s "
        "AND COALESCE(NumeroPedido, 0) <> 0 "
        "ORDER BY FechaAlbaran DESC, EjercicioAlbaran DESC, SerieAlbaran DESC, NumeroAlbaran DESC"
    )
    with connect_sqlserver() as connection, connection.cursor() as cursor:
        sql = _delivery_registration_sql(connection, sql)
        cursor.execute(sql, (str(customer_code).strip(),))
        rows = cursor.fetchall()
    return [{
        "order_number": _document_id(row.get("EjercicioPedido"), row.get("SeriePedido"), row.get("NumeroPedido")),
        "delivery_number": _document_id(row.get("EjercicioAlbaran"), row.get("SerieAlbaran"), row.get("NumeroAlbaran")),
        "attended_at": _delivery_attended_at(row),
        "delivered_at": row.get("FechaEntrega"),
        "invoiced_at": row.get("FechaFactura"),
        "is_printed": int(row.get("StatusImpresion") or 0) == -1,
        "is_invoiced": int(row.get("StatusFacturado") or 0) == -1 and int(row.get("NumeroFactura") or 0) > 0,
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
        f"FechaFactura, EjercicioFactura, SerieFactura, NumeroFactura, EjercicioPedido, SeriePedido, NumeroPedido FROM {schema}.{table} WHERE "
        + " OR ".join(conditions) +
        " ORDER BY FechaAlbaran DESC, EjercicioAlbaran DESC, SerieAlbaran DESC, NumeroAlbaran DESC"
    )
    with connect_sqlserver() as connection, connection.cursor() as cursor:
        sql = _delivery_registration_sql(connection, sql)
        cursor.execute(sql, tuple(parameters))
        rows = cursor.fetchall()
    return [{
        "order_number": _document_id(row.get("EjercicioPedido"), row.get("SeriePedido"), row.get("NumeroPedido")),
        "delivery_number": _document_id(row.get("EjercicioAlbaran"), row.get("SerieAlbaran"), row.get("NumeroAlbaran")),
        "attended_at": _delivery_attended_at(row),
        "delivered_at": row.get("FechaEntrega"),
        "invoiced_at": row.get("FechaFactura"),
        "is_printed": int(row.get("StatusImpresion") or 0) == -1,
        "is_invoiced": int(row.get("StatusFacturado") or 0) == -1 and int(row.get("NumeroFactura") or 0) > 0,
    } for row in rows]


def fetch_customer_invoices(customer_code: str, limit: int = 200, document_number: str = "",
                            date_from: date | None = None, date_to: date | None = None) -> list[dict]:
    """Consulta facturas de venta directamente en EXITERP."""
    schema = _identifier(SALES_DOCUMENTS["schema"])
    table = _identifier(SALES_DOCUMENTS["invoice_header"])
    tax_table = _identifier(SALES_DOCUMENTS["invoice_tax"])
    due_dates = ", ".join(f"i.FechaVencimiento{index}" for index in range(1, 13))
    filters_sql, filter_parameters = _document_filters("f", "Factura", document_number, date_from, date_to)
    sql = (
        f"SELECT TOP {max(1, min(limit, 1000))} f.EjercicioFactura, f.SerieFactura, f.NumeroFactura, "
        "f.FechaFactura, f.FechaRegistro, f.CodigoCliente, f.IdDelegacion, f.BaseImponible, "
        "f.TotalCuotaIva AS TaxTotal, f.ImporteFactura, f.StatusCartera, f.Documento, "
        f"COALESCE({due_dates}) AS FechaVencimiento FROM {schema}.{table} f "
        f"LEFT JOIN {schema}.{tax_table} i ON i.CodigoEmpresa=f.CodigoEmpresa "
        "AND i.EjercicioFactura=f.EjercicioFactura AND i.SerieFactura=f.SerieFactura "
        "AND i.NumeroFactura=f.NumeroFactura "
        "WHERE LTRIM(RTRIM(CONVERT(varchar(100), f.CodigoCliente)))=%s " + filters_sql + " "
        "ORDER BY f.FechaFactura DESC, f.EjercicioFactura DESC, f.SerieFactura DESC, f.NumeroFactura DESC"
    )
    with connect_sqlserver() as connection, connection.cursor() as cursor:
        cursor.execute(sql, tuple([str(customer_code).strip(), *filter_parameters]))
        rows = cursor.fetchall()
    return [{
        "id": _document_id(row["EjercicioFactura"], row["SerieFactura"], row["NumeroFactura"]),
        "number": f'{row["EjercicioFactura"]}-{str(row["SerieFactura"]).strip()}-{row["NumeroFactura"]}',
        "created_at": row.get("FechaFactura") or row.get("FechaRegistro"),
        "due_date": row.get("FechaVencimiento"),
        "subtotal": float(row.get("BaseImponible") or 0),
        "tax_total": float(row.get("TaxTotal") or 0),
        "total": float(row.get("ImporteFactura") or 0),
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
    rows = fetch_catalog_articles_by_codes(article_codes, active_only=False)
    return {
        code: {
            "with_tax": float(row["price_with_tax"] or 0),
            "without_tax": float(row["price_without_tax"] or 0),
        }
        for code, row in rows.items()
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
