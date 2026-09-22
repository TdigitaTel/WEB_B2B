import sys

from app.erp_db import fetch_product_price


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python -m scripts.check_sqlserver_price CODIGO_ARTICULO")
    code = sys.argv[1].strip()
    price = fetch_product_price(code)
    print({"status": "ok" if price else "not_found", "article_code": code, "price": price})


if __name__ == "__main__":
    main()
