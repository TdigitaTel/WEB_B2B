from app.erp_db import connect_sqlserver


def main():
    with connect_sqlserver() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT @@SERVERNAME AS server_name, DB_NAME() AS database_name")
            row = cursor.fetchone()
    print({"status": "ok", **row})


if __name__ == "__main__":
    main()
