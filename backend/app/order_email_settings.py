"""Operator configuration for customer-facing order status mail.

This module persists preferences and sends an explicit test message only. A status
change dispatcher is deliberately not claimed to exist by the API or interface.
"""
import base64
import hashlib
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from typing import Literal
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy.orm import Session
from .auth import audit, require_roles
from .config import settings
from .db import get_db
from .models import OrderEmailSettings, User

router = APIRouter(prefix="/api/v1/store/order-email-settings", tags=["Correo de pedidos"])
operator = require_roles("OPERADOR_TIENDA", "ADMIN")
STATES = {
    "PENDIENTE": "Pedido recibido",
    "EN_PREPARACION": "En preparación",
    "PENDIENTE_RECOGIDA_PARCIAL": "Pendiente de recogida parcial",
    "PENDIENTE_RECOGIDA_TOTAL": "Pendiente de recogida total",
    "ENTREGADO_PARCIAL": "Entregado parcial",
    "ENTREGADO_TOTAL": "Entregado total",
    "FACTURADO": "Facturado",
    "ELIMINADO_EN_EXIT": "No se va a atender",
}


def email_address(value):
    value = value.strip()
    if len(value) > 254 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}", value):
        raise ValueError("Escribe una dirección de correo válida")
    return value


class MailConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sender_name: str = Field(default="Bermúdez Ulloa", min_length=1, max_length=100)
    sender_email: str = "info@bermudezulloa.es"
    reply_to: str = "info@bermudezulloa.es"
    smtp_host: str = Field(default="", max_length=253)
    smtp_port: int = Field(default=587, ge=1, le=65535, strict=True)
    security: Literal["STARTTLS", "SSL"] = "STARTTLS"
    username: str = Field(default="info@bermudezulloa.es", max_length=254)
    portal_url: str = "https://extranet.bermudezulloa.es/"
    selected_states: list[str] = Field(default_factory=lambda: list(STATES), max_length=len(STATES))

    @field_validator("sender_email", "reply_to")
    @classmethod
    def valid_address(cls, value):
        return email_address(value)

    @field_validator("sender_name", "username")
    @classmethod
    def no_headers(cls, value):
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("No se admiten saltos de línea ni caracteres de control")
        return value.strip()

    @field_validator("smtp_host")
    @classmethod
    def valid_host(cls, value):
        value = value.strip()
        if value and not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", value):
            raise ValueError("Escribe el servidor SMTP sin protocolo, puerto ni ruta")
        return value

    @field_validator("portal_url")
    @classmethod
    def valid_url(cls, value):
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or any(c.isspace() for c in value):
            raise ValueError("Escribe la dirección pública HTTPS de la extranet")
        return value.rstrip("/") + "/"

    @field_validator("selected_states")
    @classmethod
    def valid_states(cls, value):
        if any(state not in STATES for state in value):
            raise ValueError("Selecciona estados visibles para el cliente")
        return list(dict.fromkeys(value))


class MailSave(MailConfiguration):
    password: SecretStr | None = None
    clear_password: bool = False


class TestMail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipient: str

    @field_validator("recipient")
    @classmethod
    def valid_recipient(cls, value):
        return email_address(value)


def cipher():
    key = hashlib.sha256(("webb2b-order-mail-v1:" + settings.jwt_secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def configuration(db):
    row = db.get(OrderEmailSettings, 1)
    return row, MailConfiguration(**(row.configuration if row else {}))


def public_settings(row, data):
    return {**data.model_dump(), "password_configured": bool(row and row.password_ciphertext),
            "available_states": STATES, "recipient_source": "CUSTOMER_RECORD",
            "automatic_dispatch_available": False}


@router.get("")
def read_settings(response: Response, db: Session = Depends(get_db), user: User = Depends(operator)):
    response.headers["Cache-Control"] = "no-store"
    return public_settings(*configuration(db))


@router.put("")
def save_settings(data: MailSave, response: Response, db: Session = Depends(get_db), user: User = Depends(operator)):
    response.headers["Cache-Control"] = "no-store"
    if data.password and len(data.password.get_secret_value()) > 2000:
        raise HTTPException(422, "La contraseña supera la longitud admitida")
    if data.clear_password and data.password and data.password.get_secret_value():
        raise HTTPException(422, "Elige sustituir o eliminar la contraseña")
    row = db.get(OrderEmailSettings, 1)
    if row is None:
        row = OrderEmailSettings(id=1)
        db.add(row)
    row.configuration = data.model_dump(exclude={"password", "clear_password"})
    changed = False
    if data.clear_password:
        row.password_ciphertext = None
        changed = True
    elif data.password and data.password.get_secret_value():
        row.password_ciphertext = cipher().encrypt(data.password.get_secret_value().encode()).decode()
        changed = True
    # Never put credentials, recipient addresses or configuration payloads in logs.
    audit(db, user, "ORDER_EMAIL_SETTINGS_UPDATED", "ORDER_EMAIL_SETTINGS", "1", {"credential_changed": changed})
    db.commit()
    return public_settings(row, MailConfiguration(**row.configuration))


@router.post("/test")
def test_mail(data: TestMail, db: Session = Depends(get_db), user: User = Depends(operator)):
    row, config = configuration(db)
    if not row or not config.smtp_host or not config.username or not row.password_ciphertext:
        raise HTTPException(409, "Guarda el servidor SMTP, el usuario y la contraseña antes de probar")
    try:
        password = cipher().decrypt(row.password_ciphertext.encode()).decode()
    except InvalidToken:
        raise HTTPException(409, "La credencial no está disponible. Guarda de nuevo la contraseña") from None
    message = EmailMessage()
    message["From"] = formataddr((config.sender_name, config.sender_email))
    message["To"] = data.recipient
    message["Reply-To"] = config.reply_to
    message["Subject"] = "Prueba de correo · Bermúdez Ulloa"
    message.set_content("Este es un correo de prueba de la configuración de la extranet.\nNo corresponde a un cambio de estado de un pedido.\n")
    try:
        context = ssl.create_default_context()
        if config.security == "SSL":
            connection = smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=15, context=context)
        else:
            connection = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=15)
        with connection as smtp:
            if config.security == "STARTTLS":
                smtp.starttls(context=context)
            smtp.login(config.username, password)
            if smtp.send_message(message):
                raise smtplib.SMTPRecipientsRefused({})
    except (smtplib.SMTPException, OSError):
        audit(db, user, "ORDER_EMAIL_TEST_FAILED", "ORDER_EMAIL_SETTINGS", "1")
        db.commit()
        raise HTTPException(502, "No se pudo enviar. Revisa servidor, puerto, seguridad, credenciales y permisos del remitente con tu proveedor") from None
    audit(db, user, "ORDER_EMAIL_TEST_SENT", "ORDER_EMAIL_SETTINGS", "1")
    db.commit()
    return {"message": "El servidor de correo ha aceptado el mensaje de prueba. Comprueba la bandeja de entrada y correo no deseado."}
