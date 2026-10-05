import hashlib
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Protocol

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from .models import Brand, Category, Customer, Product, SyncStatus
from .search import normalize_query


logger = logging.getLogger(__name__)


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

    def classification_codes(self, family: str | None = None, area_id: int | None = None,
                             family_id: int | None = None, subfamily_id: int | None = None,
                             product_type_id: int | None = None) -> list[str] | None:
        """Devuelve los SKU admitidos por filtros PostgreSQL; None significa sin filtro."""
        if not any((family, area_id, family_id, subfamily_id, product_type_id)):
            return None
        stmt = select(Product.sku)
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
        return list(self.db.scalars(stmt).all())


class PostgresPriceService:
    def price_for(self, product: Product, customer: Customer) -> Decimal:
        discount = customer.get("discount_pct", 0) if isinstance(customer, dict) else customer.discount_pct
        multiplier = Decimal("1") - (Decimal(str(discount)) / Decimal("100"))
        return (Decimal(product.list_price) * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _fallback_ean(code: str) -> str:
    number = int(hashlib.sha1(code.encode("utf-8")).hexdigest()[:14], 16) % 10**11
    return f"29{number:011d}"


def ensure_catalog_products(db: Session, articles: list[dict]) -> dict[str, Product]:
    """Garantiza el ID local estable que necesitan carrito, pedidos e imágenes."""
    codes = list(dict.fromkeys(article["article_code"] for article in articles if article.get("article_code")))
    if not codes:
        return {}
    products = {product.sku: product for product in db.scalars(
        select(Product).options(joinedload(Product.brand), joinedload(Product.category)).where(Product.sku.in_(codes))
    ).unique().all()}
    missing = [code for code in codes if code not in products]
    changed = False
    if missing:
        logger.warning(
            "CATALOG_METADATA_MISSING count=%s article_codes=%s",
            len(missing),
            ",".join(missing),
        )
        brand = db.scalar(select(Brand).where(Brand.name == "SIN MARCA"))
        if not brand:
            brand = Brand(name="SIN MARCA")
            db.add(brand)
            db.flush()
        category = db.scalar(select(Category).where(Category.name == "SIN CLASIFICAR"))
        if not category:
            category = Category(name="SIN CLASIFICAR", slug="material-sin-clasificar")
            db.add(category)
            db.flush()
        by_code = {article["article_code"]: article for article in articles}
        for code in missing:
            article = by_code[code]
            description = article.get("description") or code
            product = Product(
                erp_id=code, sku=code, manufacturer_reference="", ean=_fallback_ean(code),
                brand_id=brand.id, category_id=category.id, family="SIN CLASIFICAR",
                subfamily="SIN CLASIFICAR", short_description=description[:240],
                original_description=description, commercial_description=description,
                technical_description="", unit=article.get("unit") or "UD", pack_size=1,
                list_price=0, tax_rate=21, attributes={},
                normalized_search=" ".join(filter(None, (
                    code, description, article.get("manufacturer_reference"),
                    article.get("brand_name"), article.get("ean"),
                ))).lower(),
                active=True, sync_status=SyncStatus.pending,
                classification_status="SIN_CLASIFICAR", source_system="EXIT_CATALOG",
            )
            db.add(product)
            products[code] = product
        changed = True
    for article in articles:
        product = products.get(article["article_code"])
        if product and product.source_system == "EXIT_CATALOG":
            description = article.get("description") or product.sku
            unit = article.get("unit") or "UD"
            normalized_search = " ".join(filter(None, (
                product.sku, description, article.get("manufacturer_reference"),
                article.get("brand_name"), article.get("ean"),
            ))).lower()
            if (
                product.original_description != description
                or product.unit != unit
                or not product.active
                or product.normalized_search != normalized_search
            ):
                product.original_description = description
                product.unit = unit
                product.active = True
                product.normalized_search = normalized_search
                changed = True
    if changed:
        db.commit()
    return products


def product_view(product: Product, customer: Customer, db: Session, stock: list[dict] | None = None,
                 erp_price: dict | None = None, erp_article: dict | None = None) -> dict:
    fallback_price = PostgresPriceService().price_for(product, customer)
    erp_price = erp_price or ({
        "with_tax": erp_article["price_with_tax"],
        "without_tax": erp_article["price_without_tax"],
    } if erp_article else None)
    price_with_tax = erp_price["with_tax"] if erp_price else float(fallback_price)
    price_without_tax = erp_price["without_tax"] if erp_price else float(product.list_price)
    stock = stock or []
    exit_name = (erp_article or {}).get("description") or product.original_description or product.short_description
    has_homologated_name = bool(
        product.short_description and product.source_system != "EXIT_CATALOG"
        and product.classification_status not in {None, "", "SIN_CLASIFICAR"}
    )
    homologated_name = product.short_description if has_homologated_name else None
    return {
        "id": product.public_id,
        "image_url": f"/api/v1/products/{product.public_id}/image",
        "sku": product.sku,
        "ean": (erp_article or {}).get("ean") or product.ean,
        "manufacturer_reference": (erp_article or {}).get("manufacturer_reference") or product.manufacturer_reference,
        "name": homologated_name or exit_name,
        "homologated_name": homologated_name,
        "original_description": exit_name,
        "brand": (erp_article or {}).get("brand_name") or product.brand.name,
        "category": product.category.name,
        "family": product.family,
        "subfamily": product.subfamily,
        "classification_status": product.classification_status,
        "classification_confidence": product.classification_confidence,
        "unit": (erp_article or {}).get("unit") or product.unit,
        "list_price": price_without_tax,
        "customer_price": price_with_tax,
        "price_with_tax": price_with_tax,
        "price_without_tax": price_without_tax,
        "tax_rate": float(product.tax_rate),
        "attributes": product.attributes,
        "stock": stock,
        "total_available": sum(item["available"] for item in stock),
    }
