import sys
from pathlib import Path

from app.erp_db import fetch_product_image, image_media_type


def main():
    if len(sys.argv) not in (2, 3):
        raise SystemExit("Uso: python -m scripts.check_sqlserver_image CODIGO_ARTICULO [ARCHIVO_SALIDA]")
    code = sys.argv[1].strip()
    data = fetch_product_image(code)
    if not data:
        print({"status": "not_found", "article_code": code})
        return
    result = {
        "status": "ok",
        "article_code": code,
        "bytes": len(data),
        "media_type": image_media_type(data),
        "first_bytes_hex": data[:16].hex().upper(),
    }
    if len(sys.argv) == 3:
        output = Path(sys.argv[2])
        output.write_bytes(data)
        result["saved_as"] = str(output)
    print(result)


if __name__ == "__main__":
    main()
