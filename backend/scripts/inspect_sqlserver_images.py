from app.config import settings
from app.erp_db import connect_sqlserver


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
            rows = cursor.fetchall()
    print({"schema": settings.sqlserver_image_schema, "table": settings.sqlserver_image_table, "columns": rows})


if __name__ == "__main__":
    main()
