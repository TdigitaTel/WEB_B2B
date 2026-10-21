"""Operator-controlled rollout of customer web accounts."""
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import re
import secrets
import smtplib
import ssl

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import audit, hash_password, require_roles, verify_password
from .config import settings
from .db import get_db
from .erp_db import fetch_access_customers, fetch_customer, fetch_access_customers_by_codes
from .models import CustomerQrAccess, AuthSession, Customer, User
from .initial_credentials import encrypt_initial, decrypt_initial

router = APIRouter(prefix="/api/v1/store/customer-access", tags=["Accesos de clientes"])
operator = require_roles("OPERADOR_TIENDA", "ADMIN")
CUSTOMER_ROLES = {"CLIENTE_ADMIN", "CLIENTE"}

class AccessAction(BaseModel):
    customer_code: str = Field(min_length=1, max_length=40)

    @field_validator("customer_code")
    @classmethod
    def clean_code(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Indica el código EXIT")
        return value

class InitialEmail(AccessAction):
    recipient: str = Field(min_length=3, max_length=200)
    initial_password: str = Field(min_length=1, max_length=200)

    @field_validator("recipient")
    @classmethod
    def validate_recipient(cls, value):
        value = value.strip()
        if not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", value):
            raise ValueError("Indica un correo válido")
        return value


def accounts_for(db, code):
    return list(db.scalars(select(User).outerjoin(Customer, User.customer_id == Customer.id).where(
        ((User.erp_customer_code == code) | (Customer.erp_id == code)), User.parent_user_id.is_(None)
    ).order_by(User.id).with_for_update(of=User)).all())


def revoke_sessions(db, users):
    ids = [user.id for user in users]
    if ids:
        db.execute(update(AuthSession).where(AuthSession.user_id.in_(ids)).values(revoked=True))


def customer_lookup(code):
    try:
        row = fetch_customer(code)
    except Exception as exc:
        raise HTTPException(503, "No se pudo consultar el cliente en EXIT") from exc
    if not row:
        raise HTTPException(404, "El cliente no existe en EXIT")
    return row


def mail_ready():
    return bool(settings.smtp_host and settings.smtp_sender)


@router.get("")
def list_access(q: str = Query("", max_length=200), after: str = Query("", max_length=40),
                enabled_only: bool = False,
                user: User = Depends(operator), db: Session = Depends(get_db)):
    if enabled_only:
        code = func.coalesce(func.nullif(func.trim(User.erp_customer_code), ""), Customer.erp_id)
        conditions = [User.parent_user_id.is_(None), User.active.is_(True), User.role.in_(CUSTOMER_ROLES), code.is_not(None), ~func.lower(User.email).endswith("@cliente.test")]
        if q.strip():
            term = q.strip().lower()
            conditions.append(func.lower(code).contains(term, autoescape=True) | func.lower(User.full_name).contains(term, autoescape=True) | func.lower(User.email).contains(term, autoescape=True) | func.lower(Customer.legal_name).contains(term, autoescape=True) | func.lower(Customer.trade_name).contains(term, autoescape=True))
        codes_query = select(code.label("code")).select_from(User).outerjoin(Customer, User.customer_id == Customer.id).where(*conditions).distinct()
        total = db.scalar(select(func.count()).select_from(codes_query.subquery())) or 0
        if after.strip():
            codes_query = codes_query.where(code > after.strip())
        codes = list(db.scalars(codes_query.order_by(code).limit(51)).all())
        has_more = len(codes) > 50
        codes = codes[:50]
        accounts = db.execute(select(User, Customer).outerjoin(Customer, User.customer_id == Customer.id).where(User.parent_user_id.is_(None), User.active.is_(True), User.role.in_(CUSTOMER_ROLES), code.in_(codes)).order_by(User.id)).all() if codes else []
        try:
            exit_customers = fetch_access_customers_by_codes(codes)
        except Exception:
            exit_customers = {}
        rows = []
        for customer_code in codes:
            matches = [(account, customer) for account, customer in accounts if ((account.erp_customer_code or "").strip() or (customer.erp_id if customer else None)) == customer_code]
            account, customer = matches[0]
            rows.append({"erp_id": customer_code, "legal_name": customer.legal_name if customer else account.full_name,
                         "trade_name": customer.trade_name if customer else account.full_name,
                         "email": customer.email if customer else (account.email if "@" in account.email else ""),
                         "enabled": True, "username": account.email,
                         "status": "Pendiente de cambiar contraseña" if all(a.must_change_password for a, _ in matches) else "Habilitado"})
        for row in rows:
            external = exit_customers.get(row["erp_id"])
            if external:
                row.update(external)
        return {"items": rows, "total": total, "next_after": codes[-1] if has_more else None, "email_available": mail_ready()}
    try:
        customers = fetch_access_customers(q.strip(), after.strip(), limit=51)
    except Exception as exc:
        raise HTTPException(503, "No se pudieron buscar los clientes en EXIT") from exc
    has_more = len(customers) > 50
    rows = customers[:50]
    codes = [row["erp_id"] for row in rows]
    users = list(db.execute(select(User, Customer.erp_id).outerjoin(Customer, User.customer_id == Customer.id).where(
        ((User.erp_customer_code.in_(codes)) | (Customer.erp_id.in_(codes))), User.parent_user_id.is_(None)
    )).all()) if codes else []
    for row in rows:
        accounts = [account for account, legacy_code in users if (account.erp_customer_code or legacy_code) == row["erp_id"]]
        active = [account for account in accounts if account.active]
        row["enabled"] = bool(active)
        row["username"] = active[0].email if active else (accounts[0].email if accounts else row["erp_id"].lower())
        row["status"] = "Pendiente de cambiar contraseña" if active and all(a.must_change_password for a in active) else ("Habilitado" if active else "Deshabilitado")
    return {"items": rows, "next_after": rows[-1]["erp_id"] if has_more else None, "email_available": mail_ready()}


@router.post("/enable")
def enable(data: AccessAction, user: User = Depends(operator), db: Session = Depends(get_db)):
    customer = customer_lookup(data.customer_code)
    accounts = accounts_for(db, data.customer_code)
    if any(account.role not in CUSTOMER_ROLES for account in accounts):
        raise HTTPException(409, "Este código está asociado a una cuenta de operaciones")
    if any(account.active for account in accounts):
        raise HTTPException(409, "El cliente ya está habilitado; se conserva su contraseña")
    account = next((a for a in accounts if a.email.lower() == data.customer_code.lower()), accounts[0] if accounts else None)
    if account is None:
        if db.scalar(select(User.id).where(func.lower(User.email) == data.customer_code.lower())):
            raise HTTPException(409, "El usuario de acceso ya pertenece a otra cuenta")
        account = User(email=data.customer_code.lower(), full_name=customer["legal_name"][:160], role="CLIENTE_ADMIN",
                       erp_customer_code=data.customer_code, active=False, password_hash="")
        db.add(account)
    password = secrets.token_urlsafe(15)
    account.password_hash = hash_password(password)
    account.initial_password_ciphertext = encrypt_initial(password)
    account.erp_customer_code = data.customer_code
    account.active = True
    account.must_change_password = True
    account.initial_password_expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.initial_password_ttl_hours)
    try:
        db.flush()
        revoke_sessions(db, accounts)
        audit(db, user, "CUSTOMER_ACCESS_ENABLED", "USER", account.public_id, {"customer_code": data.customer_code})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "La cuenta ha cambiado; actualiza la búsqueda e inténtalo de nuevo") from exc
    return {"customer_code": data.customer_code, "customer_name": customer["legal_name"], "username": account.email,
            "initial_password": password, "expires_at": account.initial_password_expires_at,
            "email": customer.get("email", ""), "email_available": mail_ready(), "url": settings.customer_portal_url}


def credentials_payload(account, customer):
    return {"customer_code": account.erp_customer_code, "customer_name": customer["legal_name"], "username": account.email,
            "initial_password": decrypt_initial(account.initial_password_ciphertext), "expires_at": account.initial_password_expires_at,
            "email": customer.get("email", ""), "email_available": mail_ready(), "url": settings.customer_portal_url}


@router.post("/initial")
def reveal_initial(data: AccessAction, user: User = Depends(operator), db: Session = Depends(get_db)):
    customer = customer_lookup(data.customer_code)
    account = next((a for a in accounts_for(db, data.customer_code) if a.active and a.role in CUSTOMER_ROLES), None)
    if not account or not account.must_change_password:
        return {"credentials": None, "message": "No hay una clave inicial pendiente"}
    expires = account.initial_password_expires_at
    if not expires or expires.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
        account.initial_password_ciphertext = None
        db.commit()
        return {"credentials": None, "message": "La clave inicial ha caducado. Genera una nueva"}
    payload = credentials_payload(account, customer)
    if not payload["initial_password"] or not verify_password(payload["initial_password"], account.password_hash):
        return {"credentials": None, "message": "La clave anterior no puede recuperarse. Genera una nueva clave inicial"}
    audit(db, user, "CUSTOMER_INITIAL_PASSWORD_VIEWED", "USER", account.public_id, {"customer_code": data.customer_code})
    db.commit()
    return {"credentials": payload, "message": "Clave inicial disponible hasta que el cliente la cambie"}


@router.post("/regenerate")
def regenerate_initial(data: AccessAction, user: User = Depends(operator), db: Session = Depends(get_db)):
    customer = customer_lookup(data.customer_code)
    accounts = accounts_for(db, data.customer_code)
    account = next((a for a in accounts if a.active and a.must_change_password and a.role in CUSTOMER_ROLES), None)
    if not account:
        raise HTTPException(409, "Solo se puede regenerar una clave inicial pendiente de cambio")
    password = secrets.token_urlsafe(15)
    account.password_hash = hash_password(password)
    account.initial_password_ciphertext = encrypt_initial(password)
    account.initial_password_expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.initial_password_ttl_hours)
    revoke_sessions(db, [account])
    audit(db, user, "CUSTOMER_INITIAL_PASSWORD_REGENERATED", "USER", account.public_id, {"customer_code": data.customer_code})
    db.commit()
    return credentials_payload(account, customer)


@router.post("/disable")
def disable(data: AccessAction, user: User = Depends(operator), db: Session = Depends(get_db)):
    customer_lookup(data.customer_code)
    accounts = accounts_for(db, data.customer_code)
    if any(account.role not in CUSTOMER_ROLES for account in accounts):
        raise HTTPException(409, "Este código está asociado a una cuenta de operaciones")
    for account in accounts:
        db.execute(update(CustomerQrAccess).where(CustomerQrAccess.user_id == account.id).values(active=False))
        account.active = False
        account.initial_password_ciphertext = None
    revoke_sessions(db, accounts)
    audit(db, user, "CUSTOMER_ACCESS_DISABLED", "CUSTOMER", data.customer_code)
    db.commit()
    return {"ok": True}


@router.post("/email")
def send_initial_email(data: InitialEmail, user: User = Depends(operator), db: Session = Depends(get_db)):
    if not mail_ready():
        raise HTTPException(503, "El envío por correo no está configurado. Puedes entregar la clave manualmente")
    account = next((a for a in accounts_for(db, data.customer_code) if a.active and a.must_change_password), None)
    if not account or not verify_password(data.initial_password, account.password_hash):
        raise HTTPException(409, "Esta clave inicial ya no es válida")
    expires = account.initial_password_expires_at
    if not expires or expires.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
        raise HTTPException(409, "La clave inicial ha caducado")
    message = EmailMessage()
    message["From"] = settings.smtp_sender
    message["To"] = data.recipient
    message["Subject"] = "Tu acceso a Bermúdez Ulloa"
    message.set_content(f"Ya puedes acceder a {settings.customer_portal_url}\n\nUsuario: {account.email}\nContraseña inicial: {data.initial_password}\n\nEn el primer acceso debes cambiar esta contraseña. La clave inicial caduca a las {expires.astimezone(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC.\nSi no has solicitado este acceso, contacta con Bermúdez Ulloa.")
    try:
        connection_type = smtplib.SMTP_SSL if settings.smtp_ssl else smtplib.SMTP
        options = {"timeout": 15}
        if settings.smtp_ssl:
            options["context"] = ssl.create_default_context()
        with connection_type(settings.smtp_host, settings.smtp_port, **options) as smtp:
            if not settings.smtp_ssl:
                smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            refused = smtp.send_message(message)
            if refused:
                raise smtplib.SMTPException("Destinatario rechazado")
    except Exception as exc:
        raise HTTPException(502, "El correo no se ha podido enviar. La clave sigue disponible para entrega manual") from exc
    audit(db, user, "CUSTOMER_INITIAL_EMAIL_SENT", "USER", account.public_id, {"customer_code": data.customer_code})
    db.commit()
    return {"ok": True}
