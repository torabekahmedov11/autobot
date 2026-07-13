"""Kriptografiya yordamchilari — Instagram token shifrlash/deshifrlash."""

from cryptography.fernet import Fernet

from app.config import get_settings


def _get_cipher() -> Fernet:
    settings = get_settings()
    return Fernet(settings.ENCRYPTION_KEY.encode())


def encrypt_token(plain_token: str) -> str:
    """Token'ni shifrlaydi (bazaga yozish uchun)."""
    return _get_cipher().encrypt(plain_token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    """Shifrlangan token'ni ochadi (API chaqirish uchun)."""
    return _get_cipher().decrypt(encrypted_token.encode()).decode()
