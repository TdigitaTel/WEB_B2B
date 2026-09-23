from app.erp_db import connect_sqlserver
from app.erp_schema import CUSTOMER


def main():
    with connect_sqlserver() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION",
            (CUSTOMER["schema"], CUSTOMER["table"]),
        )
        columns = cursor.fetchall()
        cursor.execute(f"SELECT COUNT(*) AS total FROM [{CUSTOMER['schema']}].[{CUSTOMER['table']}]")
        total = cursor.fetchone()["total"]
    print({"table": f"{CUSTOMER['schema']}.{CUSTOMER['table']}", "total": total, "columns": columns})


if __name__ == "__main__":
    main()
