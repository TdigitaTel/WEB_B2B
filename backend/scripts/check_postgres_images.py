from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Product


def main():
    with SessionLocal() as db:
        total = db.scalar(select(func.count(Product.id))) or 0
        with_image = db.scalar(select(func.count(Product.id)).where(Product.image_data.is_not(None))) or 0
        by_provider = db.execute(
            select(Product.image_source_provider, func.count(Product.id))
            .where(Product.image_data.is_not(None))
            .group_by(Product.image_source_provider)
            .order_by(func.count(Product.id).desc())
        ).all()
    print({
        "total_products": total,
        "with_postgres_image": with_image,
        "missing": total - with_image,
        "coverage_percent": round((with_image / total * 100) if total else 0, 2),
        "by_provider": [{"provider": provider, "count": count} for provider, count in by_provider],
    })


if __name__ == "__main__":
    main()
