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
    if datetime.now(timezone.utc) - last_activity >= timedelta(minutes=1):
        raise HTTPException(401, "La sesión ha caducado por inactividad")
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
