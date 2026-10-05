import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import require_roles
from .db import get_db
from .models import Product, ProductImageMissing, User


router = APIRouter(tags=["catalog-images"])


@router.get("/api/v1/store/catalog-images/missing.csv")
def download_missing_product_images(
    _: User = Depends(require_roles("OPERADOR_TIENDA", "ADMIN")),
    db: Session = Depends(get_db),
):
    """Descarga la cola de revisión; nunca importa ni modifica imágenes."""
    rows = db.execute(
        select(ProductImageMissing, Product)
        .join(Product, Product.id == ProductImageMissing.product_id)
        .where(ProductImageMissing.status != "CARGADA")
        .order_by(ProductImageMissing.id)
    ).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow((
        "codigo_material",
        "nombre_actual",
        "motivo",
        "estado",
        "image_url",
        "image_path",
        "proveedor",
        "aprobado",
    ))
    for missing, product in rows:
        writer.writerow((
            product.sku,
            product.short_description,
            missing.reason or "",
            missing.status,
            "",
            "",
            "",
            "NO",
        ))
    content = "\ufeff" + output.getvalue()
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="imagenes_pendientes.csv"'},
    )
