import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPrimaryKey


class AuditLog(UUIDPrimaryKey, Base):
    """Append-only history of every significant action, including work-order status transitions.

    Order by `seq`, never by `timestamp` alone: several entries are often written in one transaction.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_entity", "entity_type", "entity_id", "timestamp"),)

    # Strictly increasing insertion order.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    previous_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    comment: Mapped[str | None] = mapped_column(Text)
    # clock_timestamp(): the moment the row is written. now() would be the transaction start for every row.
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp(),
                                                nullable=False)
