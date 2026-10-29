import hashlib
import io
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session
from .auth import current_user, require_roles
from .db import get_db
from .models import CatalogAreaVisibility, MaterialArea, MaterialAreaImage, Product, User

router = APIRouter(prefix="/api/v1/store/category-visibility", tags=["catalog"])
image_router = APIRouter(prefix="/api/v1/catalog/category-images", tags=["catalog"])

def optimized_image(content):
    with Image.open(io.BytesIO(content)) as image:
        image.thumbnail((640, 640), Image.Resampling.LANCZOS)
        converted = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
        output = io.BytesIO()
        converted.save(output, format='WEBP', quality=80, method=6)
        return output.getvalue()


def image_urls(db):
    return {area_id: f"/api/v1/catalog/category-images/{area_id}?v={digest}"
            for area_id, digest in db.execute(select(MaterialAreaImage.area_id, MaterialAreaImage.sha256)).all()}

UNCLASSIFIED_CODE = "__UNCLASSIFIED__"

def unclassified_visible(db):
    return db.scalar(select(CatalogAreaVisibility.visible).where(CatalogAreaVisibility.code == UNCLASSIFIED_CODE)) is True

def unclassified_area_ids(db):
    return select(MaterialArea.id).where(or_(MaterialArea.code == UNCLASSIFIED_CODE,
        func.upper(func.trim(MaterialArea.name)).in_(["SIN CLASIFICAR", "SIN CATEGORIA", "SIN CATEGORÍA"])))

def hidden_areas(db):
    condition = CatalogAreaVisibility.visible.is_(False)
    hidden = select(CatalogAreaVisibility.area_id).where(condition)
    return hidden.union(unclassified_area_ids(db)) if not unclassified_visible(db) else hidden

def visible_catalog_codes(db, codes=None):
    """La maestra sigue siendo EXIT; PostgreSQL delimita qué clasificación se publica."""
    allow_unclassified=unclassified_visible(db)
    if allow_unclassified and codes is None:return None
    hidden=hidden_areas(db)
    if allow_unclassified:
        # Unknown EXIT articles belong to the explicitly enabled unclassified group.
        # Known hidden categories must still be excluded from explicit worklists.
        stmt=select(Product.sku).where(Product.material_area_id.in_(hidden))
    else:
        stmt=select(Product.sku).where(Product.material_area_id.is_not(None),Product.material_area_id.not_in(hidden))
    if codes is None:return list(db.scalars(stmt).all())
    matched=set()
    for offset in range(0,len(codes),1000):
        matched.update(db.scalars(stmt.where(Product.sku.in_(codes[offset:offset+1000]))).all())
    return [code for code in codes if (code not in matched if allow_unclassified else code in matched)]

def hidden_codes(db):
    return list(db.scalars(select(Product.sku).where(Product.material_area_id.in_(hidden_areas(db)))).all())

class VisibilityIn(BaseModel):
    visible: bool

@router.get("")
def list_categories(db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "OPERADOR_TIENDA"))):
    unclassified = db.scalar(select(MaterialArea).where(MaterialArea.code == UNCLASSIFIED_CODE))
    if unclassified is None:
        unclassified = MaterialArea(code=UNCLASSIFIED_CODE, name="Artículos sin categoría")
        db.add(unclassified)
        db.flush()
    areas = db.scalars(select(MaterialArea).order_by(MaterialArea.name)).all()
    controls = {row.area_id: row for row in db.scalars(select(CatalogAreaVisibility)).all()}
    for area in areas:
        if area.id not in controls:
            row = CatalogAreaVisibility(area_id=area.id, code=area.code, name=area.name, visible=area.code != UNCLASSIFIED_CODE)
            db.add(row)
            controls[area.id] = row
    db.commit()
    images = image_urls(db)
    unclassified_ids = set(db.scalars(unclassified_area_ids(db)).all())
    return [{"id":area.id,"code":area.code,"name":area.name,"visible":controls[area.id].visible,"image_url":images.get(area.id)} for area in areas if area.code == UNCLASSIFIED_CODE or area.id not in unclassified_ids]


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
    content = optimized_image(content)
    mime_type = "image/webp"
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
