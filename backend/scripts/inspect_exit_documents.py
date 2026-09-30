"""Localiza tablas y columnas de albaranes/facturas en EXITERP sin modificar datos."""

from app.erp_db import connect_sqlserver


PATTERNS = ("%albar%", "%factur%")


def main() -> None:
    with connect_sqlserver() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE "
            "FROM INFORMATION_SCHEMA.TABLES "
            "WHERE LOWER(TABLE_NAME) LIKE %s OR LOWER(TABLE_NAME) LIKE %s "
            "ORDER BY TABLE_SCHEMA, TABLE_NAME",
            PATTERNS,
        )
        tables = cursor.fetchall()
        print({"status": "ok", "tables_found": len(tables)})
        for table in tables:
            schema = str(table["TABLE_SCHEMA"])
            name = str(table["TABLE_NAME"])
            cursor.execute(
                "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH "
                "FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION",
                (schema, name),
            )
            columns = cursor.fetchall()
            print({
                "schema": schema,
                "table": name,
                "type": table["TABLE_TYPE"],
                "columns": [
                    {
                        "name": column["COLUMN_NAME"],
                        "type": column["DATA_TYPE"],
                        "nullable": column["IS_NULLABLE"],
                        "length": column["CHARACTER_MAXIMUM_LENGTH"],
                    }
                    for column in columns
                ],
            })


if __name__ == "__main__":
    main()
