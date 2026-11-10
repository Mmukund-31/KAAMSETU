from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, CreatedAt, UUIDPrimaryKey


class Site(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "sites"

    name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    location: Mapped[str | None] = mapped_column(String(255))
