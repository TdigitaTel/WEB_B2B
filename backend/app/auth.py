from datetime import datetime, timedelta, timezone
import uuid

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Cookie, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import AuditEvent, AuthSession, User

hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_access_token(user: User, db: Session) -> str:
    now = datetime.now(timezone.utc)
    session_id = str(uuid.uuid4())
    db.add(AuthSession(id=session_id, user_id=user.id, last_activity_at=now))
    payload = {
        "sub": str(user.id),
        "jti": session_id,
        "erp_customer_code": user.erp_customer_code,
        "role": user.role,
        "iat": now,
        "exp": now + timedelta(hours=8),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def current_user(
    request: Request,
    b2b_access: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    token = b2b_access
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    if not token:
        raise HTTPException(401, "Debes iniciar sesión")
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        user = db.get(User, int(payload["sub"]))
    except Exception as exc:
        raise HTTPException(401, "Sesión inválida o caducada") from exc
    if not user or not user.active:
        raise HTTPException(401, "Usuario inactivo")
    session = db.get(AuthSession, payload.get("jti", ""))
    if not session or session.revoked or session.user_id != user.id:
        raise HTTPException(401, "Sesión inválida o caducada")
    last_activity = session.last_activity_at
    if last_activity.tzinfo is None:
        last_activity = last_activity.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - last_activity >= timedelta(minutes=settings.session_idle_timeout_minutes):
        raise HTTPException(401, "La sesión ha caducado por inactividad")
    if user.must_change_password:
        deadline = user.initial_password_expires_at
        if deadline and deadline.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
            raise HTTPException(401, "La clave inicial ha caducado. Contacta con Bermúdez Ulloa")
        allowed = {"/api/v1/account", "/api/v1/account/password", "/api/v1/auth/logout", "/api/v1/auth/activity"}
        if request.url.path not in allowed:
            raise HTTPException(403, "Debes cambiar tu contraseña inicial antes de continuar")
    from .operator_permissions import check_operator_path
    check_operator_path(user, db, request.url.path, request.method)
    from .account_permissions import effective_permissions
    permissions = effective_permissions(user, db)
    path = request.url.path
    if path == "/api/v1/account/preferences" and not permissions["can_manage_preferences"]:
        raise HTTPException(403, "Tu cuenta principal no permite cambiar estas preferencias")
    kind = request.query_params.get("kind", "").upper()
    if path.startswith("/api/v1/documents/"):
        if "/ALBARAN/" in path.upper(): kind = "ALBARAN"
        elif "/FACTURA/" in path.upper(): kind = "FACTURA"
        if not permissions["can_view_prices"]:
            raise HTTPException(403, "La descarga contiene precios que tu usuario no puede consultar")
        if ((kind == "ALBARAN" and not permissions["can_view_delivery_notes"])
                or (kind == "FACTURA" and not permissions["can_view_invoices"])
                or (not kind and not (permissions["can_view_delivery_notes"] and permissions["can_view_invoices"]))):
            raise HTTPException(403, "Tu usuario no tiene permiso para consultar estos documentos")
    if (path == "/api/v1/delivery-notes" and not permissions["can_view_delivery_notes"]) or (path == "/api/v1/invoices" and not permissions["can_view_invoices"]):
        raise HTTPException(403, "Tu usuario no tiene permiso para consultar estos documentos")
    request.state.hide_prices = not permissions["can_view_prices"]
    request.state.document_permissions = permissions
    request.state.auth_session = session
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "No tienes permisos para realizar esta acción")
        return user
    return dependency


def audit(db: Session, user: User | None, action: str, entity_type: str, entity_id: str | None = None, metadata: dict | None = None):
    db.add(AuditEvent(
        user_id=user.id if user else None,
        customer_id=user.customer_id if user else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_json=metadata or {},
    ))
