"""Password hashing (argon2id) and JWT access tokens (PyJWT)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import get_settings

_hasher = PasswordHasher()

# Used to spend the same time verifying when the email is unknown (prevents user enumeration by timing).
_DUMMY_HASH = _hasher.hash("kaamsetu-timing-equaliser")

TOKEN_TYPE_ACCESS = "access"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def create_access_token(
    user_id: uuid.UUID, role: str, expires_delta: timedelta | None = None
) -> tuple[str, datetime]:
    settings = get_settings()
    now = datetime.now(UTC)
    expires_at = now + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "type": TOKEN_TYPE_ACCESS,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    token = jwt.encode(payload, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm)
    return token, expires_at


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a token. Raises jwt.ExpiredSignatureError or jwt.InvalidTokenError."""
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.jwt_secret_key.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "iat", "sub"]},
    )
    if payload.get("type") != TOKEN_TYPE_ACCESS:
        raise jwt.InvalidTokenError("Wrong token type")
    return payload
