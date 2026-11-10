import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    false,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, CreatedAt, Timestamps, UUIDPrimaryKey
from app.models.enums import (
    EquipmentCategory,
    LanguageCode,
    Priority,
    ProductionImpact,
    ReportChannel,
    WorkOrderStatus,
)
from app.models.equipment import Equipment
from app.models.types import pg_enum
from app.models.user import User


class WorkOrder(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "work_orders"
    __table_args__ = (
        Index("ix_work_orders_status_priority", "status", "priority"),
        Index("ix_work_orders_created_at", "created_at"),
    )

    # Human-friendly sequential number, shown as WO-1001.
    number: Mapped[int] = mapped_column(Integer, Identity(start=1001), unique=True, nullable=False)
    equipment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("equipment.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    reported_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)

    issue_description: Mapped[str] = mapped_column(Text, nullable=False)
    issue_category: Mapped[EquipmentCategory] = mapped_column(
        pg_enum(EquipmentCategory, "equipment_category"), nullable=False
    )
    symptoms: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False, default=list, server_default="{}")
    priority: Mapped[Priority] = mapped_column(pg_enum(Priority, "priority"), nullable=False)
    priority_rule: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[WorkOrderStatus] = mapped_column(
        pg_enum(WorkOrderStatus, "work_order_status"), nullable=False,
        default=WorkOrderStatus.REPORTED, server_default=WorkOrderStatus.REPORTED.value,
    )
    production_impact: Mapped[ProductionImpact] = mapped_column(
        pg_enum(ProductionImpact, "production_impact"), nullable=False
    )
    safety_concern: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    report_channel: Mapped[ReportChannel] = mapped_column(pg_enum(ReportChannel, "report_channel"), nullable=False)
    location_note: Mapped[str | None] = mapped_column(String(255))
    # Client-generated idempotency key; a replayed submission returns 409 instead of a duplicate order.
    submission_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    equipment: Mapped[Equipment] = relationship(lazy="joined")
    reporter: Mapped[User] = relationship(foreign_keys=[reported_by], lazy="joined")
    assignee: Mapped[User | None] = relationship(foreign_keys=[assigned_to], lazy="joined")
    evidence: Mapped["WorkOrderEvidence | None"] = relationship(back_populates="work_order", uselist=False)

    @property
    def display_number(self) -> str:
        return f"WO-{self.number}"


class WorkOrderEvidence(UUIDPrimaryKey, CreatedAt, Base):
    """Immutable record of what was actually said and first extracted. Never updated by app code."""

    __tablename__ = "work_order_evidence"

    work_order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    # report_id from the signed evidence token: one report can become at most one work order.
    report_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)
    original_transcript: Mapped[str] = mapped_column(Text, nullable=False)
    detected_language: Mapped[str | None] = mapped_column(String(32))
    selected_language: Mapped[LanguageCode | None] = mapped_column(pg_enum(LanguageCode, "language_code"))
    extracted_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    prisma_request_id: Mapped[str | None] = mapped_column(String(128))
    prisma_model: Mapped[str | None] = mapped_column(String(64))
    audio_reference: Mapped[str | None] = mapped_column(String(512))

    work_order: Mapped[WorkOrder] = relationship(back_populates="evidence")


class Assignment(UUIDPrimaryKey, Base):
    __tablename__ = "assignments"

    work_order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    technician_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    assigned_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp(),
                                                  nullable=False)
    comments: Mapped[str | None] = mapped_column(Text)
