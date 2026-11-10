"""Request dependencies: DB session, current user, role checks.

The user's identity and role always come from the database row referenced by the
verified token, never from anything the client sends in the request body.
"""

import uuid
from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, Unauthorized
from app.core.security import decode_access_token
from app.database.session import get_db
from app.models import User, UserRole

_bearer = HTTPBearer(auto_error=False, description="Paste the access_token from POST /api/v1/auth/login")

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise Unauthorized()
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = uuid.UUID(payload["sub"])
    except jwt.ExpiredSignatureError as exc:
        raise Unauthorized("Session expired. Please log in again.", code="token_expired") from exc
    except (jwt.InvalidTokenError, ValueError, KeyError) as exc:
        raise Unauthorized("Invalid authentication token", code="invalid_token") from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise Unauthorized("Account not found or disabled", code="invalid_token")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    allowed = set(roles)

    def checker(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise Forbidden(
                "You do not have permission to perform this action",
                code="insufficient_role",
                details={"required": sorted(r.value for r in allowed)},
            )
        return user

    return checker


SupervisorOrManager = Annotated[User, Depends(require_roles(UserRole.SUPERVISOR, UserRole.MANAGER))]
ManagerOnly = Annotated[User, Depends(require_roles(UserRole.MANAGER))]
