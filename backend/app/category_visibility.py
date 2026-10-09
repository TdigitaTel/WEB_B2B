from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from .auth import require_roles
from .db import get_db
from .models import CatalogAreaVisibility, MaterialArea, Product, User

router = APIRouter(prefix="/api/v1/store/category-visibility", tags=["catalog"])

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
    return [{"id":area.id,"code":area.code,"name":area.name,"visible":controls[area.id].visible} for area in areas]

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
