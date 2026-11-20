from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return _password_hash.verify(plain_password, hashed_password)
    except Exception:
        # 哈希格式异常时视为验证失败，避免返回 500
        return False


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    expire_minutes = expires_minutes or settings.access_token_expire_minutes
    payload = {
        "sub": subject,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub"]},
    )
