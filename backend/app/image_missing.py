import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Product, ProductImageMissing


logger = logging.getLogger(__name__)


def record_missing_product_image(db: Session, product: Product, reason: str) -> None:
    """Registra una imagen pendiente sin interrumpir la consulta del catálogo."""
    try:
        row = db.scalar(
            select(ProductImageMissing).where(ProductImageMissing.product_id == product.id)
        )
        if row is None:
            db.add(
                ProductImageMissing(
                    product_id=product.id,
                    sku=product.sku,
                    status="PENDIENTE",
                    reason=reason,
                )
            )
            db.commit()
            logger.warning(
                "Imagen PostgreSQL pendiente para el material %s: %s",
                product.sku,
                reason,
            )
            return

        changed = False
        if row.status == "CARGADA":
            row.status = "PENDIENTE"
            changed = True
        if row.reason != reason:
            row.reason = reason
            changed = True
        if row.sku != product.sku:
            row.sku = product.sku
            changed = True
        if changed:
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("No se pudo registrar la imagen pendiente del material %s", product.sku)


def mark_product_image_loaded(db: Session, product: Product) -> None:
    row = db.scalar(
        select(ProductImageMissing).where(ProductImageMissing.product_id == product.id)
    )
    if row and row.status != "CARGADA":
        row.status = "CARGADA"
        row.reason = None

