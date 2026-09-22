import sys

from app.config import settings
from app.erp_db import fetch_product_stock


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python -m scripts.check_sqlserver_stock CODIGO_ARTICULO")
    code = sys.argv[1].strip()
    stock = fetch_product_stock(code)
    print({
        "status": "ok",
        "article_code": code,
        "excluded_warehouses": [value.strip() for value in settings.sqlserver_stock_excluded_warehouses.split(",") if value.strip()],
        "total_available": sum(item["available"] for item in stock),
        "warehouses": stock,
    })


if __name__ == "__main__":
    main()
