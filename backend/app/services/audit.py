"""Append-only audit trail. Callers add the row inside their own transaction."""

import uuid
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.models import AuditLog


def record(
    db: Session,
    *,
    actor_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    previous_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    comment: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        previous_value=jsonable_encoder(previous_value) if previous_value is not None else None,
        new_value=jsonable_encoder(new_value) if new_value is not None else None,
        comment=comment,
    )
    db.add(entry)
    return entry
