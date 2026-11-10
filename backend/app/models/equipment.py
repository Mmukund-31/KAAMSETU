import re
import uuid

from sqlalchemy import Boolean, ForeignKey, String, false
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.database.base import Base, CreatedAt, UUIDPrimaryKey
from app.models.enums import EquipmentCategory, OperationalStatus
from app.models.site import Site
from app.models.types import pg_enum


def normalize_equipment_code(code: str) -> str:
    """'m 204', 'M-204', 'm204' -> 'M204'. Used for tolerant, exact-match lookup."""
    return re.sub(r"[^A-Z0-9]", "", code.upper())


class Equipment(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "equipment"

    equipment_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    code_normalized: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[EquipmentCategory] = mapped_column(
        pg_enum(EquipmentCategory, "equipment_category"), nullable=False, index=True
    )
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True)
    location: Mapped[str | None] = mapped_column(String(160))
    operational_status: Mapped[OperationalStatus] = mapped_column(
        pg_enum(OperationalStatus, "operational_status"), nullable=False,
        default=OperationalStatus.RUNNING, server_default=OperationalStatus.RUNNING.value,
    )
    is_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())

    site: Mapped[Site] = relationship(lazy="joined")

    @validates("equipment_code")
    def _set_normalized(self, _key: str, value: str) -> str:
        value = value.strip().upper()
        self.code_normalized = normalize_equipment_code(value)
        return value
