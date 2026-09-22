from app.erp_db import connect_sqlserver
from app.erp_schema import ARTICLE, STOCK, WAREHOUSE


def main():
    expected = [
        (STOCK["schema"], STOCK["table"]),
        (WAREHOUSE["schema"], WAREHOUSE["table"]),
        (ARTICLE["schema"], ARTICLE["table"]),
    ]
    result = {}
    with connect_sqlserver() as connection:
        with connection.cursor() as cursor:
            for schema, table in expected:
                cursor.execute(
                    """
                    SELECT COLUMN_NAME, DATA_TYPE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = %s AND LOWER(TABLE_NAME) = LOWER(%s)
                    ORDER BY ORDINAL_POSITION
                    """,
                    (schema, table),
                )
                result[f"{schema}.{table}"] = cursor.fetchall()
    print(result)


if __name__ == "__main__":
    main()
