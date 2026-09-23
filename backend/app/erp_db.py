import pymssql
import re

from .config import settings
from .erp_schema import ARTICLE, CUSTOMER, IMAGE, STOCK, WAREHOUSE


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
            selections.append(f"c.{_identifier(column)} AS [{field}]" if column else f"NULL AS [{field}]")
        code_column = _identifier(columns["code"])
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
            "store_code": "00 + 99",
            "store": "Almeiras + KARDEX",
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
