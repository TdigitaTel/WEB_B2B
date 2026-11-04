"""Operator configuration for customer-facing order status mail.

This module persists preferences and sends an explicit test message only. A status
change dispatcher is deliberately not claimed to exist by the API or interface.
"""
import base64
import hashlib
import logging
import json
from uuid import uuid4
import re
import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from typing import Literal
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Response, Query
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy.orm import Session
from .auth import audit, require_roles
from .config import settings
from .db import get_db
from .models import OrderEmailSettings, User

router = APIRouter(prefix="/api/v1/store/order-email-settings", tags=["Correo de pedidos"])
operator = require_roles("OPERADOR_TIENDA", "ADMIN")
from .order_status_email import STATES, example_email
from .order_email_texts import LABELS, MESSAGES
from .order_email_content import EmailContent


def email_address(value):
    value = value.strip()
    if len(value) > 254 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}", value):
        raise ValueError("Escribe una dirección de correo válida")
    return value


class MailConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: EmailContent = Field(default_factory=EmailContent)
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
    preview_state: str = "ENTREGADO_PARCIAL"

    @field_validator("preview_state")
    @classmethod
    def valid_state(cls, value):
        if value not in LABELS:
            raise ValueError("Estado no disponible")
        return value

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
            "automatic_dispatch_available": False, "content_states": LABELS, "content_suggestions": MESSAGES}


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


@router.get("/preview")
def preview_mail(response: Response, state: str = Query(default="ENTREGADO_PARCIAL"),
                 db: Session = Depends(get_db), user: User = Depends(operator)):
    response.headers["Cache-Control"] = "no-store"
    if state not in LABELS:
        raise HTTPException(422, "Estado no disponible")
    _, config = configuration(db)
    return example_email(state, config.portal_url, content=config.content)


class PreviewDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: str
    content: EmailContent

    @field_validator("state")
    @classmethod
    def valid_state(cls, value):
        if value not in LABELS:
            raise ValueError("Estado no disponible")
        return value


@router.post("/preview")
def preview_draft(data: PreviewDraft, response: Response, db: Session = Depends(get_db), user: User = Depends(operator)):
    response.headers["Cache-Control"] = "no-store"
    _, config = configuration(db)
    return example_email(data.state, config.portal_url, content=data.content)


def smtp_failure(exc, phase):
    """Operator-safe diagnosis: never return the provider response or credentials."""
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return 'AUTH_REJECTED', 'El servidor rechazó la autenticación SMTP. Revisa el usuario y las credenciales, y confirma qué método de acceso permite el proveedor; la cuenta puede requerir OAuth.'
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return 'SENDER_REJECTED', 'El servidor rechazó el correo de origen. La cuenta autenticada debe tener permiso para enviar con ese remitente.'
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return 'RECIPIENT_REJECTED', 'El servidor rechazó el destinatario de prueba. Revisa esa dirección y los permisos de envío a destinatarios externos.'
    if isinstance(exc, smtplib.SMTPDataError):
        return 'MESSAGE_REJECTED', 'El servidor rechazó el mensaje. Consulta con el proveedor los límites y las políticas de envío de esta cuenta.'
    if isinstance(exc, ssl.SSLCertVerificationError):
        return 'CERTIFICATE_INVALID', 'No se pudo verificar el certificado del servidor SMTP. Revisa el nombre del servidor y su certificado con el proveedor.'
    if isinstance(exc, ssl.SSLError):
        return 'TLS_FAILED', 'Falló la conexión segura con el servidor SMTP. Confirma que el puerto corresponde a la seguridad configurada: STARTTLS o SSL directo.'
    if isinstance(exc, socket.gaierror):
        return 'HOST_NOT_FOUND', 'No se pudo resolver el nombre del servidor SMTP desde el servidor de la extranet. Revisa el nombre configurado y el DNS del servidor.'
    if isinstance(exc, TimeoutError):
        return 'TIMEOUT', 'El servidor SMTP no respondió a tiempo. Revisa el puerto, la conectividad y las restricciones de salida del servidor de la extranet.'
    if isinstance(exc, ConnectionRefusedError):
        return 'CONNECTION_REFUSED', 'El servidor SMTP rechazó la conexión. Revisa el servidor, el puerto y las reglas de red o cortafuegos.'
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        if phase == 'TLS':
            return 'STARTTLS_UNAVAILABLE', 'El servidor no ofrece STARTTLS en este puerto. Confirma el puerto y el tipo de seguridad con tu proveedor.'
        return 'AUTH_UNAVAILABLE', 'El servidor no ofrece un método de autenticación compatible con esta conexión. Consulta los requisitos SMTP de tu proveedor.'
    stage = {'CONNECT':'conectar con el servidor', 'TLS':'negociar la conexión segura', 'AUTH':'autenticar la cuenta', 'SEND':'enviar el mensaje'}[phase]
    return 'SMTP_FAILED', f'No se pudo {stage}. Revisa con tu proveedor la conexión SMTP y sus permisos. No se ha confirmado el envío.'


def smtp_diagnostic(exc, phase, config, password, recipient):
    """Only exception replies, never an SMTP transcript (AUTH can contain secrets)."""
    def sanitize(value):
        value = value.decode('utf-8', errors='replace') if isinstance(value, bytes) else str(value)
        credentials = [password, config.username, config.sender_email, recipient]
        credentials += [base64.b64encode(password.encode()).decode(),
                        base64.b64encode(config.username.encode()).decode(),
                        base64.b64encode(('\0'+config.username+'\0'+password).encode()).decode()]
        for secret in sorted(set(filter(None, credentials)), key=len, reverse=True):
            value = value.replace(secret, '[oculto]')
        value = re.sub(r'(?i)\b(?:bearer|authorization|password|passwd|token|secret)\s*[:= ]+\S+', '[credencial oculta]', value)
        value = re.sub(r'[A-Za-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+', '[correo oculto]', value)
        return ' '.join(value.split())[:1500]
    smtp_code = getattr(exc, 'smtp_code', None)
    reply = getattr(exc, 'smtp_error', None)
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        replies = list(exc.recipients.values())[:5]
        reply = ' | '.join(f'{code} {sanitize(reason)}' for code, reason in replies)
    return {'reference':uuid4().hex[:12], 'phase':phase, 'exception':type(exc).__name__,
            'smtp_code':smtp_code if isinstance(smtp_code,int) else None,
            'response':sanitize(reply if reply is not None else str(exc))}


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
    template = example_email(data.preview_state, config.portal_url, content=config.content)
    message["Subject"] = "[PRUEBA] " + template["subject"]
    message.set_content(template["text"])
    message.add_alternative(template["html"], subtype="html")
    phase = 'CONNECT'
    try:
        context = ssl.create_default_context()
        if config.security == "SSL":
            connection = smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=15, context=context)
        else:
            connection = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=15)
        with connection as smtp:
            if config.security == "STARTTLS":
                phase = 'TLS'
                smtp.starttls(context=context)
            phase = 'AUTH'
            smtp.login(config.username, password)
            phase = 'SEND'
            refused = smtp.send_message(message)
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)
    except (smtplib.SMTPException, OSError) as exc:
        code, explanation = smtp_failure(exc, phase)
        diagnostic = smtp_diagnostic(exc, phase, config, password, data.recipient)
        diagnostic['code'] = code
        logging.getLogger(__name__).warning('ORDER_EMAIL_TEST_FAILED %s', json.dumps(diagnostic, ensure_ascii=False))
        audit(db, user, "ORDER_EMAIL_TEST_FAILED", "ORDER_EMAIL_SETTINGS", "1", diagnostic)
        db.commit()
        detail = (explanation + '\n\nDiagnóstico SMTP · Referencia ' + diagnostic['reference']
                  + '\nFase: ' + phase + ' · Librería: ' + diagnostic['exception']
                  + (' · Código SMTP: ' + str(diagnostic['smtp_code']) if diagnostic['smtp_code'] is not None else '')
                  + '\nRespuesta: ' + diagnostic['response'])
        raise HTTPException(502, detail, headers={"X-Mail-Error":code}) from None
    audit(db, user, "ORDER_EMAIL_TEST_SENT", "ORDER_EMAIL_SETTINGS", "1")
    db.commit()
    return {"message": "El servidor de correo ha aceptado el mensaje de prueba. Comprueba la bandeja de entrada y correo no deseado."}
