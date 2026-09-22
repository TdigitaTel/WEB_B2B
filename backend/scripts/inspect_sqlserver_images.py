from app.config import settings
import re

from app.erp_db import connect_sqlserver


def identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise RuntimeError(f"Identificador no válido: {value}")
    return f"[{value}]"


def main():
    with connect_sqlserver() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %s AND LOWER(TABLE_NAME) = LOWER(%s)
                ORDER BY ORDINAL_POSITION
                """,
                (settings.sqlserver_image_schema, settings.sqlserver_image_table),
            )
            columns = cursor.fetchall()
            names = {row["COLUMN_NAME"].lower(): row["COLUMN_NAME"] for row in columns}
            image_name = names.get(settings.sqlserver_image_column.lower())
            key_name = names.get(settings.sqlserver_image_key_column.lower())
            summary = None
            samples = []
            if image_name:
                qualified = f"{identifier(settings.sqlserver_image_schema)}.{identifier(settings.sqlserver_image_table)}"
                cursor.execute(
                    f"SELECT COUNT(*) AS total_rows, "
                    f"SUM(CASE WHEN {identifier(image_name)} IS NOT NULL AND DATALENGTH({identifier(image_name)}) > 0 THEN 1 ELSE 0 END) AS rows_with_image "
                    f"FROM {qualified}"
                )
                summary = cursor.fetchone()
                if key_name:
                    cursor.execute(
                        f"SELECT TOP 10 CAST({identifier(key_name)} AS varchar(100)) AS article_key, "
                        f"DATALENGTH({identifier(image_name)}) AS image_bytes "
                        f"FROM {qualified} WHERE {identifier(image_name)} IS NOT NULL "
                        f"ORDER BY DATALENGTH({identifier(image_name)}) DESC"
                    )
                    samples = cursor.fetchall()
    print({
        "configured": {
            "schema": settings.sqlserver_image_schema,
            "table": settings.sqlserver_image_table,
            "key_column": settings.sqlserver_image_key_column,
            "image_column": settings.sqlserver_image_column,
        },
        "columns": columns,
        "configured_key_found": bool(key_name),
        "configured_image_found": bool(image_name),
        "summary": summary,
        "samples": samples,
    })


if __name__ == "__main__":
    main()
