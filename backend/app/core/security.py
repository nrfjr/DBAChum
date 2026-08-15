import hashlib
import secrets

from pwdlib import PasswordHash

from functools import lru_cache

from cryptography.fernet import Fernet

from app.core.config import settings


password_hash = PasswordHash.recommended()


def hash_password(
    password: str,
) -> str:
    return password_hash.hash(password)


def verify_password(
    password: str,
    hashed_password: str,
) -> bool:
    return password_hash.verify(
        password,
        hashed_password,
    )


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(
    token: str,
) -> str:
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()
    
@lru_cache
def get_connection_cipher() -> Fernet:
    return Fernet(settings.connection_encryption_key.encode("utf-8"))


def encrypt_secret(value: str) -> str:
    cipher = get_connection_cipher()
    return cipher.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    cipher = get_connection_cipher()
    return cipher.decrypt(value.encode("utf-8")).decode("utf-8")