import pymssql
import re

from .config import settings


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


def fetch_product_image(article_code: str) -> bytes | None:
    schema = _identifier(settings.sqlserver_image_schema)
    table = _identifier(settings.sqlserver_image_table)
    key_column = _identifier(settings.sqlserver_image_key_column)
    image_column = _identifier(settings.sqlserver_image_column)
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
    return bytes(row["image_data"])


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
