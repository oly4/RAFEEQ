from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from rafeeq_backend.config import get_settings
from rafeeq_backend.models import RefreshToken, User, utc_now
from rafeeq_backend.modules.auth.domain.schemas import RegisterRequest, TokenPair, UserResponse
from rafeeq_backend.modules.auth.infrastructure.security import (
    create_jwt,
    decode_jwt,
    hash_password,
    token_hash,
    verify_password,
)


def register_user(db: Session, request: RegisterRequest) -> User:
    email = request.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(
        role=request.role,
        full_name=request.full_name.strip(),
        email=email,
        password_hash=hash_password(request.password),
        locale=request.locale,
        timezone=request.timezone,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return user


def issue_tokens(db: Session, user: User) -> TokenPair:
    access, _ = create_jwt(user.id, user.role, "access")
    refresh, refresh_expires = create_jwt(user.id, user.role, "refresh")
    db.add(
        RefreshToken(user_id=user.id, token_hash=token_hash(refresh), expires_at=refresh_expires)
    )
    db.commit()
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=get_settings().jwt_access_ttl_minutes * 60,
        user=UserResponse.model_validate(user),
    )


def rotate_tokens(db: Session, raw_token: str) -> TokenPair:
    payload = decode_jwt(raw_token, "refresh")
    record = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash(raw_token)))
    if record is None or record.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked"
        )
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked"
        )
    user = db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account unavailable")
    record.revoked_at = utc_now()
    db.commit()
    return issue_tokens(db, user)


def revoke_token(db: Session, raw_token: str) -> None:
    record = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash(raw_token)))
    if record and record.revoked_at is None:
        record.revoked_at = utc_now()
        db.commit()
