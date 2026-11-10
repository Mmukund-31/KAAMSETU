import uuid

from sqlalchemy import Boolean, ForeignKey, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, CreatedAt, UUIDPrimaryKey
from app.models.enums import LanguageCode, UserRole
from app.models.site import Site
from app.models.types import pg_enum


class User(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Always stored lower-cased by the service layer.
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(pg_enum(UserRole, "user_role"), nullable=False, index=True)
    preferred_language: Mapped[LanguageCode] = mapped_column(
        pg_enum(LanguageCode, "language_code"), nullable=False, default=LanguageCode.EN,
        server_default=LanguageCode.EN.value,
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())

    site: Mapped[Site | None] = relationship(lazy="joined")

    def __repr__(self) -> str:  # never include the hash
        return f"<User {self.email} role={self.role}>"
