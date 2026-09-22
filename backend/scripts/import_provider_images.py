import csv
import hashlib
import sys

import httpx
from sqlalchemy import select

from app.db import SessionLocal
from app.erp_db import image_media_type, normalize_image_data
from app.models import Product


MAX_IMAGE_BYTES = 10 * 1024 * 1024


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python -m scripts.import_provider_images /ruta/imagenes.csv")
    imported = skipped = failed = 0
    with open(sys.argv[1], encoding="utf-8-sig", newline="") as file, SessionLocal() as db, httpx.Client(follow_redirects=True, timeout=30) as client:
        for row in csv.DictReader(file):
            sku = (row.get("sku") or "").strip()
            url = (row.get("image_url") or "").strip()
            provider = (row.get("provider") or "Proveedor oficial").strip()
            product = db.scalar(select(Product).where(Product.sku == sku))
            if not product or not url:
                skipped += 1
                continue
            try:
                response = client.get(url, headers={"User-Agent": "BermudezUlloa-CatalogImageImporter/1.0"})
                response.raise_for_status()
                if len(response.content) > MAX_IMAGE_BYTES:
                    raise ValueError("Imagen superior a 10 MB")
                data = normalize_image_data(response.content)
                media_type = image_media_type(data)
                if not media_type.startswith("image/"):
                    raise ValueError("El archivo descargado no es una imagen compatible")
                product.image_data = data
                product.image_media_type = media_type
                product.image_source_url = str(response.url)
                product.image_source_provider = provider
                product.image_sha256 = hashlib.sha256(data).hexdigest()
                db.commit()
                imported += 1
            except Exception as exc:
                db.rollback()
                failed += 1
                print({"sku": sku, "status": "error", "detail": str(exc)})
    print({"status": "ok", "imported": imported, "skipped": skipped, "failed": failed})


if __name__ == "__main__":
    main()
