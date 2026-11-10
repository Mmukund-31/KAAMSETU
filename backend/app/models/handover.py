import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, CreatedAt, UUIDPrimaryKey
from app.models.enums import HandoverStatus
from app.models.types import pg_enum


class Handover(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "handovers"
    __table_args__ = (Index("ix_handovers_site_created", "site_id", "created_at"),)

    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    shift_identifier: Mapped[str] = mapped_column(String(64), nullable=False)
    # Verbatim notes or transcript; the generated summary is stored separately.
    original_notes: Mapped[str] = mapped_column(Text, nullable=False)
    detected_language: Mapped[str | None] = mapped_column(String(32))
    generated_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    pending_actions: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[HandoverStatus] = mapped_column(
        pg_enum(HandoverStatus, "handover_status"), nullable=False,
        default=HandoverStatus.SUBMITTED, server_default=HandoverStatus.SUBMITTED.value,
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_comment: Mapped[str | None] = mapped_column(Text)
