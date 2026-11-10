"""User management rules."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, Unprocessable
from app.core.security import hash_password
from app.models import Site, User, UserRole
from app.schemas.user import UserCreate
from app.services import audit

# Which roles each role may create. Self-registration does not exist: every account is created by someone accountable.
_CREATABLE_ROLES: dict[UserRole, set[UserRole]] = {
    UserRole.MANAGER: {UserRole.TECHNICIAN, UserRole.SUPERVISOR, UserRole.MANAGER},
    UserRole.SUPERVISOR: {UserRole.TECHNICIAN},
    UserRole.TECHNICIAN: set(),
}


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.strip().lower()))


def get_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    return db.get(User, user_id)


def create_user(db: Session, actor: User, data: UserCreate) -> User:
    if data.role not in _CREATABLE_ROLES[actor.role]:
        raise Forbidden(
            f"A {actor.role.value} cannot create a {data.role.value} account",
            code="role_not_permitted",
        )
    if get_by_email(db, data.email):
        raise Conflict("An account with this email already exists", code="email_taken")

    site_id = data.site_id or actor.site_id
    if site_id is not None and db.get(Site, site_id) is None:
        raise Unprocessable("Site does not exist", code="unknown_site", details={"site_id": str(site_id)})
    if actor.role != UserRole.MANAGER and site_id != actor.site_id:
        raise Forbidden("Supervisors can only create accounts for their own site", code="site_not_permitted")

    user = User(
        name=data.name.strip(),
        email=data.email,
        password_hash=hash_password(data.password),
        role=data.role,
        preferred_language=data.preferred_language,
        site_id=site_id,
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        actor_id=actor.id,
        action="user.create",
        entity_type="user",
        entity_id=user.id,
        new_value={"email": user.email, "role": user.role, "site_id": user.site_id, "name": user.name},
    )
    db.commit()
    db.refresh(user)
    return user
