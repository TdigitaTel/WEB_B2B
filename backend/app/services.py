from decimal import Decimal, ROUND_HALF_UP
from typing import Protocol

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from .models import Customer, Inventory, Product, Store
from .search import normalize_query


class ProductService(Protocol):
    def search(self, query: str, page: int, page_size: int, family: str | None,
               area_id: int | None = None, family_id: int | None = None,
               subfamily_id: int | None = None, product_type_id: int | None = None): ...


class PriceService(Protocol):
    def price_for(self, product: Product, customer: Customer) -> Decimal: ...


class StockService(Protocol):
    def stock_for(self, product_id: int) -> list[dict]: ...


class PostgresCatalogService:
    def __init__(self, db: Session):
        self.db = db

    def searchable(self, column):
        if self.db.bind.dialect.name == "postgresql":
            return func.unaccent(func.lower(column))
        for accented, plain in zip("áéíóúüñ", "aeiouun"):
            column = func.replace(column, accented, plain)
        return func.lower(column)

    def text_condition(self, query: str):
        raw = " ".join(query.lower().strip().split())
        normalized = normalize_query(query)
        if not normalized:
            return None
        return or_(
            func.lower(Product.sku) == raw,
            Product.sku.ilike(f"{raw}%"),
            Product.ean.ilike(f"{raw}%"),
            and_(*(self.searchable(Product.normalized_search).ilike(f"%{term}%", escape="\\") for term in normalized.split())),
        )

    def direct_description_condition(self, query: str):
        """Match words against product-owned text, without classification labels."""
        normalized = normalize_query(query)
        if not normalized:
            return None
        direct_text = (
            func.coalesce(Product.short_description, "") + " " +
            func.coalesce(Product.original_description, "") + " " +
            func.coalesce(Product.technical_description, "") + " " +
            func.coalesce(Product.manufacturer_reference, "")
        )
        return and_(*(self.searchable(direct_text).ilike(f"%{term}%", escape="\\") for term in normalized.split()))

    def search(self, query: str = "", page: int = 1, page_size: int = 24, family: str | None = None,
               area_id: int | None = None, family_id: int | None = None,
               subfamily_id: int | None = None, product_type_id: int | None = None):
        stmt = select(Product).options(joinedload(Product.brand), joinedload(Product.category)).where(Product.active.is_(True))
        raw = " ".join(query.lower().strip().split())
        normalized = normalize_query(query)
        if normalized:
            direct_condition = self.direct_description_condition(query)
            has_direct_matches = self.db.scalar(
                select(Product.id).where(Product.active.is_(True), direct_condition).limit(1)
            ) is not None
            stmt = stmt.where(direct_condition if has_direct_matches else self.text_condition(query)).order_by(
                (func.lower(Product.sku) == raw).desc(),
                self.searchable(Product.short_description).ilike(f"{normalized}%", escape="\\").desc(),
                and_(*(self.searchable(Product.short_description).ilike(f"%{term}%", escape="\\") for term in normalized.split())).desc(),
                Product.sku.ilike(f"{raw}%").desc(),
                Product.short_description,
            )
        else:
            stmt = stmt.order_by(Product.family, Product.short_description)
        if family:
            stmt = stmt.where(Product.family == family)
        if area_id:
            stmt = stmt.where(Product.material_area_id == area_id)
        if family_id:
            stmt = stmt.where(Product.material_family_id == family_id)
        if subfamily_id:
            stmt = stmt.where(Product.material_subfamily_id == subfamily_id)
        if product_type_id:
            stmt = stmt.where(Product.material_product_type_id == product_type_id)
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = self.db.scalar(count_stmt) or 0
        rows = self.db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).unique().all()
        return rows, total


class PostgresPriceService:
    def price_for(self, product: Product, customer: Customer) -> Decimal:
        multiplier = Decimal("1") - (Decimal(customer.discount_pct) / Decimal("100"))
        return (Decimal(product.list_price) * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class PostgresStockService:
    def __init__(self, db: Session):
        self.db = db

    def stock_for(self, product_id: int):
        rows = self.db.execute(
            select(Inventory, Store).join(Store, Store.id == Inventory.store_id)
            .where(Inventory.product_id == product_id, Store.active.is_(True)).order_by(Store.name)
        ).all()
        return [{
            "store_id": store.public_id,
            "store_code": store.code,
            "store": store.name,
            "physical": float(inv.physical_qty),
            "reserved": float(inv.reserved_qty),
            "available": float(inv.physical_qty - inv.reserved_qty),
            "updated_at": inv.updated_source_at,
        } for inv, store in rows]


def product_view(product: Product, customer: Customer, db: Session) -> dict:
    price = PostgresPriceService().price_for(product, customer)
    stock = PostgresStockService(db).stock_for(product.id)
    return {
        "id": product.public_id,
        "sku": product.sku,
        "ean": product.ean,
        "manufacturer_reference": product.manufacturer_reference,
        "name": product.short_description,
        "original_description": product.original_description,
        "brand": product.brand.name,
        "category": product.category.name,
        "family": product.family,
        "subfamily": product.subfamily,
        "classification_status": product.classification_status,
        "classification_confidence": product.classification_confidence,
        "unit": product.unit,
        "list_price": float(product.list_price),
        "customer_price": float(price),
        "tax_rate": float(product.tax_rate),
        "attributes": product.attributes,
        "stock": stock,
        "total_available": sum(item["available"] for item in stock),
    }
