import sys

from app.erp_db import fetch_product_image, image_media_type


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python -m scripts.check_sqlserver_image CODIGO_ARTICULO")
    code = sys.argv[1].strip()
    data = fetch_product_image(code)
    if not data:
        print({"status": "not_found", "article_code": code})
        return
    print({
        "status": "ok",
        "article_code": code,
        "bytes": len(data),
        "media_type": image_media_type(data),
        "first_bytes_hex": data[:16].hex().upper(),
    })


if __name__ == "__main__":
    main()
