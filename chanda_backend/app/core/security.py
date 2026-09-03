from datetime import datetime, timedelta, timezone
from typing import Optional, Literal
import secrets

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def create_token(
    subject: str,
    role: str,
    token_type: Literal["access", "refresh"] = "access",
    expires_minutes: Optional[int] = None,
) -> str:
    if expires_minutes is None:
        expires_minutes = (
            settings.ACCESS_TOKEN_EXPIRE_MINUTES
            if token_type == "access"
            else settings.REFRESH_TOKEN_EXPIRE_MINUTES
        )
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Raises jose.JWTError if invalid/expired."""
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def generate_reset_token() -> str:
    """Random URL-safe token for the forgot-password flow (stored hashed in DB)."""
    return secrets.token_urlsafe(48)
