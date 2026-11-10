import re
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from app.models.enums import LanguageCode, UserRole
from app.schemas.common import ORMModel

# Deliberately simple: we only need a plausible address, not RFC 5322 (avoids an extra dependency).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z0-9-]{2,}$")


def _normalize_email(value: str) -> str:
    value = value.strip().lower()
    if not _EMAIL_RE.match(value):
        raise ValueError("Invalid email address")
    return value


def _check_password_strength(value: str) -> str:
    if not (re.search(r"[A-Za-z]", value) and re.search(r"\d", value)):
        raise ValueError("Password must contain at least one letter and one digit")
    return value


Email = Annotated[str, Field(max_length=254), AfterValidator(_normalize_email)]
Password = Annotated[str, Field(min_length=8, max_length=128), AfterValidator(_check_password_strength)]


class SiteOut(ORMModel):
    id: uuid.UUID
    name: str
    location: str | None


class UserOut(ORMModel):
    id: uuid.UUID
    name: str
    email: str
    role: UserRole
    preferred_language: LanguageCode
    site_id: uuid.UUID | None
    site: SiteOut | None
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: Email
    password: Password
    role: UserRole
    preferred_language: LanguageCode = LanguageCode.EN
    # Defaults to the creating user's site when omitted.
    site_id: uuid.UUID | None = None
