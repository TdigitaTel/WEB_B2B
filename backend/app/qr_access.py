"""Revocable customer QR credentials. Secrets never enter query strings or logs."""
import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderSVG
from .auth import audit, require_roles
from .config import settings
from .db import get_db
from .models import CustomerQrAccess, User
from .customer_access import accounts_for, AccessAction, CUSTOMER_ROLES

router = APIRouter(tags=["Acceso QR"])
operator = require_roles("OPERADOR_TIENDA", "ADMIN")


def cipher():
    key = hashlib.sha256(("webb2b-qr-access-v1:"+settings.jwt_secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


class QrAction(AccessAction):
    regenerate: bool = False


class QrLogin(BaseModel):
    token: str = Field(min_length=40, max_length=200)


def eligible(db, code):
    accounts = [a for a in accounts_for(db, code) if a.role in CUSTOMER_ROLES and a.active]
    if len(accounts) != 1:
        raise HTTPException(409, "El cliente debe tener una única cuenta activa para generar su QR")
    return accounts[0]


@router.post("/api/v1/store/customer-access/qr")
def customer_qr(data: QrAction, response: Response, actor: User = Depends(operator), db: Session = Depends(get_db)):
    account = eligible(db, data.customer_code)
    record = db.scalar(select(CustomerQrAccess).where(CustomerQrAccess.user_id == account.id).with_for_update())
    now = datetime.now(timezone.utc)
    if not record:
        record = CustomerQrAccess(user_id=account.id)
        db.add(record)
    if not record.id or data.regenerate or not record.active or record.expires_at.replace(tzinfo=timezone.utc) <= now:
        secret = secrets.token_urlsafe(32)
        record.secret_hash = hashlib.sha256(secret.encode()).hexdigest()
        record.secret_ciphertext = cipher().encrypt(secret.encode()).decode()
        record.active = True
        record.expires_at = now+timedelta(days=90)
        db.flush()
        audit(db, actor, "CUSTOMER_QR_GENERATED", "USER", account.public_id)
    secret = cipher().decrypt(record.secret_ciphertext.encode()).decode()
    token = record.id+"."+secret
    parts = urlsplit(settings.customer_portal_url)
    link = urlunsplit((parts.scheme, parts.netloc, parts.path or "/", "", "qr="+token))
    qr = QrCodeWidget(link, barLevel='M')
    bounds = qr.getBounds(); size = bounds[2]-bounds[0]
    drawing = Drawing(300, 300, transform=[300/size, 0, 0, 300/size, 0, 0])
    drawing.add(qr)
    svg = renderSVG.drawToString(drawing).encode()
    response.headers["Cache-Control"] = "no-store"
    db.commit()
    return {"image": "data:image/svg+xml;base64,"+base64.b64encode(svg).decode(), "url": link,
            "expires_at": record.expires_at, "customer_code": data.customer_code}


@router.post("/api/v1/store/customer-access/qr/revoke")
def revoke_qr(data: AccessAction, actor: User = Depends(operator), db: Session = Depends(get_db)):
    for account in accounts_for(db, data.customer_code):
        record = db.scalar(select(CustomerQrAccess).where(CustomerQrAccess.user_id == account.id))
        if record:
            record.active = False
            audit(db, actor, "CUSTOMER_QR_REVOKED", "USER", account.public_id)
    db.commit()
    return {"ok": True}


@router.post("/api/v1/auth/qr")
def login_qr(data: QrLogin, response: Response, db: Session = Depends(get_db)):
    identifier, _, secret = data.token.partition(".")
    record = db.get(CustomerQrAccess, identifier)
    now = datetime.now(timezone.utc)
    if not record or not record.active or record.expires_at.replace(tzinfo=timezone.utc) <= now or not hmac.compare_digest(record.secret_hash, hashlib.sha256(secret.encode()).hexdigest()):
        raise HTTPException(401, "QR inválido, deshabilitado o caducado")
    account = db.get(User, record.user_id)
    if not account or not account.active or account.role not in CUSTOMER_ROLES:
        raise HTTPException(401, "El acceso del cliente está deshabilitado")
    from .main import complete_login
    audit(db, account, "LOGIN_QR", "USER", account.public_id)
    response.headers["Cache-Control"] = "no-store"
    return complete_login(account, response, db)
