import re
import sys
from pathlib import Path

from app.erp_db import connect_sqlserver, image_media_type, normalize_image_data
from app.erp_schema import IMAGE


SEARCHABLE_TYPES = {
    "bigint", "char", "decimal", "int", "nchar", "numeric", "nvarchar",
    "smallint", "tinyint", "uniqueidentifier", "varchar",
}

EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/webp": ".webp",
}


def identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise RuntimeError(f"Identificador no valido: {value}")
    return f"[{value}]"


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python -m scripts.find_sqlserver_image CODIGO")

    code = sys.argv[1].strip()
    schema = identifier(IMAGE["schema"])
    table = identifier(IMAGE["table"])
    image_column = identifier(IMAGE["data"])
    qualified_table = f"{schema}.{table}"
    matches = []
    image_data = None

    with connect_sqlserver() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COLUMN_NAME, DATA_TYPE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %s AND LOWER(TABLE_NAME) = LOWER(%s)
                ORDER BY ORDINAL_POSITION
                """,
                (IMAGE["schema"], IMAGE["table"]),
            )
            columns = cursor.fetchall()

            for column in columns:
                if column["DATA_TYPE"].lower() not in SEARCHABLE_TYPES:
                    continue
                column_name = identifier(column["COLUMN_NAME"])
                cursor.execute(
                    f"SELECT TOP 1 {image_column} AS image_data, "
                    f"DATALENGTH({image_column}) AS image_bytes "
                    f"FROM {qualified_table} "
                    f"WHERE LTRIM(RTRIM(CONVERT(varchar(200), {column_name}))) = %s",
                    (code,),
                )
                row = cursor.fetchone()
                if row:
                    matches.append({
                        "column": column["COLUMN_NAME"],
                        "image_bytes": row["image_bytes"],
                    })
                    if image_data is None and row["image_data"]:
                        image_data = bytes(row["image_data"])

    result = {"status": "not_found", "searched_value": code, "matches": matches}
    if image_data:
        data = normalize_image_data(image_data)
        media_type = image_media_type(data)
        extension = EXTENSIONS.get(media_type, ".bin")
        output = Path(f"/tmp/sqlserver_image_{code}{extension}")
        output.write_bytes(data)
        result.update({
            "status": "ok" if media_type.startswith("image/") else "unknown_format",
            "media_type": media_type,
            "bytes": len(data),
            "first_bytes_hex": data[:16].hex().upper(),
            "saved_as": str(output),
        })
    elif matches:
        result["status"] = "found_without_image"

    print(result)


if __name__ == "__main__":
    main()
