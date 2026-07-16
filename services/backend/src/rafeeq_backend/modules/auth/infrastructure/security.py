from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any
from uuid import uuid4

import jwt
from fastapi import HTTPException, status
from pwdlib import PasswordHash

from rafeeq_backend.config import get_settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _secret(kind: str) -> str:
    settings = get_settings()
    value = settings.jwt_access_secret if kind == "access" else settings.jwt_refresh_secret
    if value is None or not value.get_secret_value():
        raise RuntimeError(f"JWT_{kind.upper()}_SECRET must be configured")
    return value.get_secret_value()


def create_jwt(user_id: str, role: str, kind: str) -> tuple[str, datetime]:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    if kind == "access":
        expires_at = now + timedelta(minutes=settings.jwt_access_ttl_minutes)
    else:
        expires_at = now + timedelta(days=settings.jwt_refresh_ttl_days)
    payload = {
        "sub": user_id,
        "role": role,
        "type": kind,
        "jti": str(uuid4()),
        "iat": now,
        "exp": expires_at,
    }
    return jwt.encode(payload, _secret(kind), algorithm="HS256"), expires_at


def decode_jwt(token: str, expected_kind: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, _secret(expected_kind), algorithms=["HS256"])
        if payload.get("type") != expected_kind:
            raise jwt.InvalidTokenError("incorrect token type")
        return payload
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc
