"""Subusuarios administrados exclusivamente por su cuenta principal."""
import re
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .auth import current_user, audit, hash_password
from .account_permissions import CUSTOMER_ROLES, official_code
from .config import settings
from .db import get_db
from .models import User, AuthSession, CustomerQrAccess
from .initial_credentials import encrypt_initial, decrypt_initial
from .qr_access import issue_qr

router = APIRouter(prefix="/api/v1/account", tags=["Subusuarios"])


def principal(actor: User = Depends(current_user)):
    if actor.parent_user_id is not None or actor.role not in CUSTOMER_ROLES:
        raise HTTPException(403, "Solo la cuenta principal puede administrar subusuarios")
    return actor


class Permissions(BaseModel):
    can_view_prices: bool = False
    can_view_delivery_notes: bool = False
    can_view_invoices: bool = False
    can_manage_preferences: bool = True
    own_orders_only: bool = True


class SubuserCreate(Permissions):
    full_name: str = Field(min_length=1, max_length=160)
    email: str = Field(min_length=3, max_length=200)
    contact_phone: str = Field(default="", max_length=40)

    @field_validator("full_name")
    @classmethod
    def name(cls, value):
        value = value.strip()
        if not value: raise ValueError("Indica el nombre")
        return value

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Indica un correo válido")
        return value


class SubuserChange(Permissions):
    active: bool
    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    email: str | None = Field(default=None, min_length=3, max_length=200)
    contact_phone: str | None = Field(default=None, max_length=40)

    @field_validator("full_name")
    @classmethod
    def name(cls, value):
        if value is None: raise ValueError("Indica el nombre")
        return SubuserCreate.name(value)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        if value is None: raise ValueError("Indica un correo válido")
        return SubuserCreate.valid_email(value)

    @field_validator("contact_phone")
    @classmethod
    def phone(cls, value):
        return (value or "").strip()


class PasswordReset(BaseModel):
    password: str | None = Field(default=None, min_length=12, max_length=200)


class QrRequest(BaseModel):
    regenerate: bool = False


def owned(db, actor, public_id):
    row = db.scalar(select(User).where(User.public_id == public_id, User.parent_user_id == actor.id).with_for_update())
    if not row: raise HTTPException(404, "Subusuario no encontrado")
    return row


def revoke(db, user, qr=False):
    db.execute(update(AuthSession).where(AuthSession.user_id == user.id).values(revoked=True))
    if qr:
        db.execute(update(CustomerQrAccess).where(CustomerQrAccess.user_id == user.id).values(active=False))


def payload(row):
    password = None
    if row.must_change_password and row.initial_password_expires_at and row.initial_password_expires_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
        password = decrypt_initial(row.initial_password_ciphertext) if row.initial_password_ciphertext else None
    return {"id":row.public_id, "full_name":row.full_name, "email":row.email, "active":row.active,
            "access_code":row.access_code, "customer_code":row.erp_customer_code, "contact_phone":row.contact_phone or "",
            **{key:bool(getattr(row,key)) for key in Permissions.model_fields},
            "must_change_password":row.must_change_password, "initial_password":password,
            "initial_password_expires_at":row.initial_password_expires_at}


def set_password(row, password):
    row.password_hash = hash_password(password)
    row.must_change_password = True
    row.initial_password_ciphertext = encrypt_initial(password)
    row.initial_password_expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.initial_password_ttl_hours)


@router.get("/subusers")
def list_subusers(actor: User = Depends(principal), db: Session = Depends(get_db)):
    return [payload(row) for row in db.scalars(select(User).where(User.parent_user_id == actor.id).order_by(User.full_name)).all()]


@router.post("/subusers", status_code=201)
def create_subuser(data: SubuserCreate, actor: User = Depends(principal), db: Session = Depends(get_db)):
    code = official_code(actor, db)
    if not code: raise HTTPException(409, "La cuenta principal no está vinculada a EXIT")
    if db.scalar(select(User.id).where(func.lower(User.email) == data.email)):
        raise HTTPException(409, "Ese correo ya tiene una cuenta de acceso")
    row = User(**data.model_dump(), parent_user_id=actor.id, customer_id=actor.customer_id,
               erp_customer_code=code, role="CLIENTE", active=True, password_hash="")
    set_password(row, secrets.token_urlsafe(15))
    db.add(row)
    try:
        db.flush()
        row.access_code = f"SU-{row.id:08d}"
        audit(db, actor, "SUBUSER_CREATED", "USER", row.public_id, {"customer_code":code})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Ese correo ya tiene una cuenta de acceso") from exc
    return payload(row)


@router.patch("/subusers/{public_id}")
def change_subuser(public_id: str, data: SubuserChange, actor: User = Depends(principal), db: Session = Depends(get_db)):
    row = owned(db, actor, public_id)
    changes = data.model_dump(exclude_unset=True)
    if "email" in changes and db.scalar(select(User.id).where(func.lower(User.email) == changes["email"], User.id != row.id)):
        raise HTTPException(409, "Ese correo ya tiene una cuenta de acceso")
    for key, value in changes.items(): setattr(row, key, value)
    revoke(db, row, qr=not row.active)
    audit(db, actor, "SUBUSER_PERMISSIONS_CHANGED", "USER", row.public_id, {key:value for key,value in changes.items() if key in Permissions.model_fields or key == "active"})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Ese correo ya tiene una cuenta de acceso") from exc
    return payload(row)


@router.post("/subusers/{public_id}/password")
def reset_subuser_password(public_id: str, data: PasswordReset, actor: User = Depends(principal), db: Session = Depends(get_db)):
    row = owned(db, actor, public_id)
    set_password(row, data.password or secrets.token_urlsafe(15))
    revoke(db, row, qr=True)
    audit(db, actor, "SUBUSER_PASSWORD_RESET", "USER", row.public_id)
    db.commit()
    return payload(row)


@router.post("/subusers/{public_id}/qr")
def subuser_qr(public_id: str, data: QrRequest, response: Response, actor: User = Depends(principal), db: Session = Depends(get_db)):
    row = owned(db, actor, public_id)
    if not row.active: raise HTTPException(409, "Habilita el subusuario antes de generar su QR")
    return issue_qr(row, actor, db, response, data.regenerate)


@router.post("/subusers/{public_id}/qr/revoke")
def revoke_subuser_qr(public_id: str, actor: User = Depends(principal), db: Session = Depends(get_db)):
    row = owned(db, actor, public_id)
    db.execute(update(CustomerQrAccess).where(CustomerQrAccess.user_id == row.id).values(active=False))
    audit(db, actor, "SUBUSER_QR_REVOKED", "USER", row.public_id)
    db.commit()
    return {"ok":True}


@router.post("/qr")
def own_qr(data: QrRequest, response: Response, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    if actor.role not in CUSTOMER_ROLES: raise HTTPException(403, "Esta opción es para cuentas de cliente")
    return issue_qr(actor, actor, db, response, data.regenerate)
