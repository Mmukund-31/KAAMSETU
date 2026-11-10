import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, CreatedAt, UUIDPrimaryKey
from app.models.enums import ChecklistResponseValue, ChecklistStatus, EquipmentCategory, pg_enum


class ChecklistTemplate(UUIDPrimaryKey, CreatedAt, Base):
    """A supervisor-approved SOP checklist. Items are company-approved text only; never AI-generated."""

    __tablename__ = "checklist_templates"
    __table_args__ = (
        UniqueConstraint("equipment_category", "work_order_type", "version"),
        # At most one active version per (category, work-order type).
        Index(
            "uq_checklist_templates_active",
            "equipment_category",
            "work_order_type",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    equipment_category: Mapped[EquipmentCategory] = mapped_column(
        pg_enum(EquipmentCategory, "equipment_category"), nullable=False
    )
    work_order_type: Mapped[str] = mapped_column(String(32), nullable=False, default="corrective", server_default="corrective")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    items: Mapped[list["ChecklistItem"]] = relationship(
        back_populates="template", order_by="ChecklistItem.sequence", cascade="all, delete-orphan"
    )


class ChecklistItem(UUIDPrimaryKey, Base):
    __tablename__ = "checklist_items"
    __table_args__ = (UniqueConstraint("template_id", "sequence"),)

    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("checklist_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    template: Mapped[ChecklistTemplate] = relationship(back_populates="items")


class WorkOrderChecklist(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "work_order_checklists"

    work_order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("checklist_templates.id", ondelete="RESTRICT"), nullable=False)
    template_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ChecklistStatus] = mapped_column(
        pg_enum(ChecklistStatus, "checklist_status"), nullable=False,
        default=ChecklistStatus.PENDING, server_default=ChecklistStatus.PENDING.value,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    template: Mapped[ChecklistTemplate] = relationship(lazy="joined")
    responses: Mapped[list["ChecklistResponse"]] = relationship(back_populates="checklist", cascade="all, delete-orphan")


class ChecklistResponse(UUIDPrimaryKey, Base):
    __tablename__ = "checklist_responses"
    __table_args__ = (UniqueConstraint("checklist_id", "checklist_item_id"),)

    checklist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_order_checklists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    checklist_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("checklist_items.id", ondelete="RESTRICT"), nullable=False)
    response: Mapped[ChecklistResponseValue] = mapped_column(
        pg_enum(ChecklistResponseValue, "checklist_response_value"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)
    completed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    checklist: Mapped[WorkOrderChecklist] = relationship(back_populates="responses")
