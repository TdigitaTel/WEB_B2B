"""Recoverable, authenticated encryption for temporary initial passwords only."""
import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken
from .config import settings

def cipher():
    key=hashlib.sha256(("webb2b-initial-password-v1:"+settings.jwt_secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))

def encrypt_initial(password):
    return cipher().encrypt(password.encode()).decode()

def decrypt_initial(value):
    try:
        return cipher().decrypt(value.encode()).decode() if value else None
    except InvalidToken:
        return None
