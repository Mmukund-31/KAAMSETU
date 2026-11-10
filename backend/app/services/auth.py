"""Authentication: verify credentials and issue access tokens."""

import logging

from sqlalchemy.orm import Session

from app.core.errors import Forbidden, Unauthorized
from app.core.security import (
    create_access_token,
    hash_password,
    password_needs_rehash,
    verify_password,
)
from app.models import User
from app.schemas.auth import TokenResponse
from app.schemas.user import UserOut
from app.services.users import get_by_email

logger = logging.getLogger("kaamsetu.auth")

_INVALID = "Invalid email or password"


def authenticate(db: Session, email: str, password: str) -> User:
    user = get_by_email(db, email)
    # verify_password runs a full hash check even when the user is unknown, so timing does not reveal accounts.
    if not verify_password(password, user.password_hash if user else None) or user is None:
        logger.info("Login failed", extra={"ctx": {"event": "login_failed"}})
        raise Unauthorized(_INVALID, code="invalid_credentials")
    if not user.is_active:
        raise Forbidden("This account is disabled", code="account_disabled")
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        db.commit()
    logger.info("Login succeeded", extra={"ctx": {"event": "login", "user_id": str(user.id), "role": user.role.value}})
    return user


def issue_token(user: User) -> TokenResponse:
    token, expires_at = create_access_token(user.id, user.role.value)
    return TokenResponse(access_token=token, expires_at=expires_at, user=UserOut.model_validate(user))
