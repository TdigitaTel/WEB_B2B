import hashlib
import io
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from .auth import current_user, require_roles
from .db import get_db
from .models import CatalogAreaVisibility, MaterialArea, MaterialAreaImage, Product, User

router = APIRouter(prefix="/api/v1/store/category-visibility", tags=["catalog"])
image_router = APIRouter(prefix="/api/v1/catalog/category-images", tags=["catalog"])

def image_urls(db):
    return {area_id: f"/api/v1/catalog/category-images/{area_id}?v={digest}"
            for area_id, digest in db.execute(select(MaterialAreaImage.area_id, MaterialAreaImage.sha256)).all()}

def hidden_areas(db):
    return select(CatalogAreaVisibility.area_id).where(CatalogAreaVisibility.visible.is_(False))

def hidden_codes(db):
    return list(db.scalars(select(Product.sku).where(Product.material_area_id.in_(hidden_areas(db)))).all())

class VisibilityIn(BaseModel):
    visible: bool

@router.get("")
def list_categories(db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "OPERADOR_TIENDA"))):
    areas = db.scalars(select(MaterialArea).order_by(MaterialArea.name)).all()
    controls = {row.area_id: row for row in db.scalars(select(CatalogAreaVisibility)).all()}
    for area in areas:
        if area.id not in controls:
            row = CatalogAreaVisibility(area_id=area.id, code=area.code, name=area.name, visible=True)
            db.add(row)
            controls[area.id] = row
    db.commit()
    images = image_urls(db)
    return [{"id":area.id,"code":area.code,"name":area.name,"visible":controls[area.id].visible,"image_url":images.get(area.id)} for area in areas]


@router.post("/{area_id}/image")
async def upload_category_image(area_id: int, file: UploadFile = File(...),
                                db: Session = Depends(get_db),
                                user: User = Depends(require_roles("ADMIN", "OPERADOR_TIENDA"))):
    if db.get(MaterialArea, area_id) is None:
        raise HTTPException(404, "Categoría no encontrada")
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "La imagen supera 10 MB")
    try:
        with Image.open(io.BytesIO(content)) as image:
            mime_type = {"PNG":"image/png", "JPEG":"image/jpeg", "WEBP":"image/webp"}.get(image.format)
            if not mime_type or image.width > 4096 or image.height > 4096:
                raise ValueError("Formato o tamaño no admitido")
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, "Utiliza una imagen PNG, JPG o WebP de hasta 4096 × 4096 píxeles") from exc
    row = db.get(MaterialAreaImage, area_id)
    if row is None:
        row = MaterialAreaImage(area_id=area_id)
        db.add(row)
    row.filename = Path(file.filename or "imagen").name[:200]
    row.mime_type, row.image_data = mime_type, content
    row.sha256 = hashlib.sha256(content).hexdigest()
    db.commit()
    return {"id":area_id,"image_url":f"/api/v1/catalog/category-images/{area_id}?v={row.sha256}"}


@image_router.get("/{area_id}")
def category_image(area_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.role not in {"ADMIN", "OPERADOR_TIENDA"} and db.scalar(select(CatalogAreaVisibility.area_id).where(
            CatalogAreaVisibility.area_id == area_id, CatalogAreaVisibility.visible.is_(False))):
        raise HTTPException(404, "Imagen no encontrada")
    row = db.get(MaterialAreaImage, area_id)
    if row is None:
        raise HTTPException(404, "Imagen no encontrada")
    return Response(content=row.image_data, media_type=row.mime_type,
                    headers={"X-Content-Type-Options":"nosniff", "Cache-Control":"no-store, private"})

@router.patch("/{area_id}")
def update_category(area_id: int, data: VisibilityIn, db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "OPERADOR_TIENDA"))):
    area = db.get(MaterialArea, area_id)
    if not area:
        raise HTTPException(404, "Categoría no encontrada")
    row = db.get(CatalogAreaVisibility, area_id)
    if not row:
        row = CatalogAreaVisibility(area_id=area.id, code=area.code, name=area.name)
        db.add(row)
    row.visible = data.visible
    db.commit()
    return {"id":area.id,"visible":row.visible}
