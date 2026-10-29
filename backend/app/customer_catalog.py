"""The customer principal chooses price prominence for its own account."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StrictBool
from sqlalchemy import text
from sqlalchemy.orm import Session
from .account_permissions import CUSTOMER_ROLES, official_code, principal_for, effective_permissions
from .auth import current_user, audit
from .db import get_db
from .models import CustomerCatalogSetting, User

router = APIRouter(prefix="/api/v1/account/catalog-price", tags=["account"])


def highlight_price_without_tax(db, customer_code):
    row = db.get(CustomerCatalogSetting, customer_code) if customer_code else None
    return bool(row and row.highlight_price_without_tax)


def own_customer_code(user, db):
    if user.role not in CUSTOMER_ROLES:
        raise HTTPException(403, "Esta preferencia la configura el cliente desde Mi cuenta")
    code = official_code(principal_for(user, db), db)
    if not code:
        raise HTTPException(403, "La cuenta no tiene un cliente asociado")
    return code


class CatalogPricePreference(BaseModel):
    model_config = {"extra": "forbid"}
    highlight_price_without_tax: StrictBool


@router.get("")
def read_preference(user: User = Depends(current_user), db: Session = Depends(get_db)):
    code = own_customer_code(user, db)
    return {"highlight_price_without_tax": highlight_price_without_tax(db, code)}


@router.patch("")
def update_preference(data: CatalogPricePreference, user: User = Depends(current_user), db: Session = Depends(get_db)):
    code = own_customer_code(user, db)
    if user.parent_user_id is not None:
        raise HTTPException(403, "El precio destacado lo elige la cuenta principal del cliente")
    if not effective_permissions(user, db)["can_manage_preferences"]:
        raise HTTPException(403, "Tu cuenta no permite cambiar preferencias")
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": "catalog-price:" + code})
    setting = db.get(CustomerCatalogSetting, code, populate_existing=True)
    if setting is None:
        setting = CustomerCatalogSetting(customer_code=code)
        db.add(setting)
    setting.highlight_price_without_tax = data.highlight_price_without_tax
    audit(db, user, "CUSTOMER_CATALOG_PRICE_CHANGED", "CUSTOMER", code,
          {"highlight_price_without_tax": data.highlight_price_without_tax})
    db.commit()
    return {"highlight_price_without_tax": setting.highlight_price_without_tax}
