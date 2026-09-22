import hashlib
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.erp_db import fetch_product_images, image_media_type
from app.models import Product


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    batch_size = 100
    copied = missing = 0
    with SessionLocal() as db:
        stmt = select(Product).where(Product.image_data.is_(None)).order_by(Product.id)
        if limit:
            stmt = stmt.limit(limit)
        products = db.scalars(stmt).all()
        for start in range(0, len(products), batch_size):
            batch = products[start:start + batch_size]
            images = fetch_product_images([product.sku for product in batch])
            for product in batch:
                data = images.get(product.sku)
                if not data or not image_media_type(data).startswith("image/"):
                    missing += 1
                    continue
                product.image_data = data
                product.image_media_type = image_media_type(data)
                product.image_source_provider = "EXITERP SQL Server"
                product.image_sha256 = hashlib.sha256(data).hexdigest()
                copied += 1
            db.commit()
            print({"processed": min(start + len(batch), len(products)), "copied": copied, "missing": missing})
    print({"status": "ok", "total": len(products), "copied": copied, "missing": missing})


if __name__ == "__main__":
    main()
