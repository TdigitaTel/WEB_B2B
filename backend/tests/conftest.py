import os
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest


# Configure a disposable database before importing any application module.  This
# keeps local runs and CI away from configured PostgreSQL databases and prevents
# one pytest invocation from leaking state into the next one.
_database_directory = tempfile.TemporaryDirectory(prefix="web-b2b-pytest-")
_database_path = Path(_database_directory.name) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{_database_path}"
os.environ.setdefault("SEED_PRODUCTS", "300")
os.environ.setdefault("SEED_CUSTOMERS", "5")


def _article(product) -> dict:
    price_without_tax = Decimal(product.list_price).quantize(Decimal("0.01"))
    return {
        "article_code": product.sku,
        "description": product.original_description or product.short_description,
        "unit": product.unit,
        "manufacturer_reference": product.manufacturer_reference,
        "brand_code": "",
        "brand_name": product.brand.name,
        "ean": product.ean,
        "price_with_tax": float((price_without_tax * Decimal("1.21")).quantize(Decimal("0.01"))),
        "price_without_tax": float(price_without_tax),
    }


@pytest.fixture(autouse=True)
def exit_erp_stub(monkeypatch):
    """Replace EXITERP reads with deterministic data backed by the test catalog."""
    from sqlalchemy import select

    from app import main as main_module
    from app.db import SessionLocal
    from app.models import Product
    from app.search import normalize_query

    def fetch_customer(customer_code: str) -> dict:
        code = str(customer_code).strip()
        return {
            "erp_id": code,
            "legal_name": f"Cliente de prueba {code}",
            "trade_name": f"Cliente {code}",
            "tax_id": "B00000000",
            "email": f"{code.lower()}@cliente.test",
            "phone": "981000000",
            "billing_address": "Dirección de prueba",
            "price_list": "PROFESIONAL",
            "discount_pct": 0.0,
        }

    def fetch_catalog_articles(query: str = "", page: int = 1, page_size: int = 24,
                               article_codes: list[str] | None = None) -> tuple[list[dict], int]:
        with SessionLocal() as db:
            statement = select(Product).where(Product.active.is_(True))
            if article_codes is not None:
                if not article_codes:
                    return [], 0
                statement = statement.where(Product.sku.in_(article_codes))
            products = list(db.scalars(statement.order_by(Product.sku)).all())
            terms = normalize_query(query).split()
            if terms:
                products = [
                    product for product in products
                    if all(term in normalize_query(" ".join(filter(None, (
                        product.sku, product.ean, product.manufacturer_reference,
                        product.short_description, product.original_description,
                        product.normalized_search, product.brand.name,
                    )))) for term in terms)
                ]
            total = len(products)
            start = (max(1, int(page)) - 1) * int(page_size)
            return [_article(product) for product in products[start:start + int(page_size)]], total

    def fetch_catalog_articles_by_codes(article_codes: list[str], active_only: bool = True) -> dict[str, dict]:
        codes = list(dict.fromkeys(str(code).strip() for code in article_codes if str(code).strip()))
        if not codes:
            return {}
        with SessionLocal() as db:
            statement = select(Product).where(Product.sku.in_(codes))
            if active_only:
                statement = statement.where(Product.active.is_(True))
            products = {product.sku: product for product in db.scalars(statement).all()}
            return {code: _article(products[code]) for code in codes if code in products}

    def fetch_product_prices(article_codes: list[str]) -> dict[str, dict]:
        return {
            code: {
                "with_tax": article["price_with_tax"],
                "without_tax": article["price_without_tax"],
            }
            for code, article in fetch_catalog_articles_by_codes(article_codes, active_only=False).items()
        }

    def fetch_product_stocks(article_codes: list[str]) -> dict[str, list[dict]]:
        warehouses = (
            ("00", "Almeiras"), ("01", "A Coruña"), ("02", "Ferrol"),
            ("04", "Santiago"), ("05", "Sanxenxo"),
        )
        return {
            str(code): [
                {"store_code": store_code, "store": store, "available": 100.0}
                for store_code, store in warehouses
            ]
            for code in article_codes
        }

    monkeypatch.setattr(main_module, "fetch_customer", fetch_customer)
    monkeypatch.setattr(main_module, "fetch_catalog_articles", fetch_catalog_articles)
    monkeypatch.setattr(main_module, "fetch_catalog_articles_by_codes", fetch_catalog_articles_by_codes)
    monkeypatch.setattr(main_module, "fetch_product_prices", fetch_product_prices)
    monkeypatch.setattr(main_module, "fetch_product_stocks", fetch_product_stocks)
    monkeypatch.setattr(main_module, "fetch_product_stock", lambda code: fetch_product_stocks([code]).get(code, []))
    monkeypatch.setattr(main_module, "fetch_customer_favorite_articles", lambda customer_code, limit=8: [])
    monkeypatch.setattr(main_module, "fetch_customer_exit_orders", lambda *args, **kwargs: [])
    monkeypatch.setattr(main_module, "fetch_customer_delivery_statuses", lambda *args, **kwargs: [])
    monkeypatch.setattr(main_module, "fetch_delivery_statuses_for_orders", lambda *args, **kwargs: [])
    monkeypatch.setattr(main_module, "fetch_exit_orders_live", lambda *args, **kwargs: [])
