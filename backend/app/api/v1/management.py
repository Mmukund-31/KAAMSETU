"""Equipment, users, checklist templates, handovers, dashboard and audit routes."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy import func, select

from app.config import get_settings
from app.core.deps import CurrentUser, DbSession, SupervisorOrManager
from app.domain.enums import EquipmentCategory, HandoverStatus, LanguageCode, UserRole
from app.gnani.prisma import PrismaClient
from app.models import AuditLog, User, WorkOrder
from app.schemas.common import ErrorResponse
from app.schemas.management import (
    AuditEntry,
    AuditPage,
    EquipmentCreate,
    EquipmentDetail,
    EquipmentIssues,
    EquipmentOut,
    EquipmentPage,
    HandoverCreate,
    HandoverDetail,
    HandoverPage,
    HandoverReview,
    Overview,
    TechnicianWorkload,
    TemplateCreate,
    TemplateItemOut,
    TemplateOut,
    TrendPoint,
    UserListItem,
)
from app.services import access, checklists, dashboard, handovers, speech
from app.services import equipment as equipment_service
from app.services.work_orders import person
from app.workflows.escalation import OPEN_STATUSES

router = APIRouter()
_ERRORS = {r: {"model": ErrorResponse} for r in (401, 403, 404, 409, 422)}

# ── equipment ────────────────────────────────────────────────────────────


@router.get("/equipment", response_model=EquipmentPage, tags=["equipment"], responses=_ERRORS)
def list_equipment(user: CurrentUser, db: DbSession, category: EquipmentCategory | None = None,
                   q: Annotated[str | None, Query(max_length=100)] = None, site_id: uuid.UUID | None = None,
                   page: Annotated[int, Query(ge=1)] = 1,
                   page_size: Annotated[int, Query(ge=1, le=200)] = 50) -> EquipmentPage:
    return equipment_service.list_equipment(db, user, category=category, q=q, site_id=site_id, page=page,
                                            page_size=page_size)


@router.get("/equipment/{equipment_id}", response_model=EquipmentDetail, tags=["equipment"], responses=_ERRORS)
def get_equipment(equipment_id: uuid.UUID, user: CurrentUser, db: DbSession) -> EquipmentDetail:
    return equipment_service.get_detail(db, user, equipment_id)


@router.post("/equipment", response_model=EquipmentOut, status_code=status.HTTP_201_CREATED, tags=["equipment"],
             responses=_ERRORS)
def create_equipment(body: EquipmentCreate, user: SupervisorOrManager, db: DbSession) -> EquipmentOut:
    return equipment_service.create(db, user, body)


# ── users ────────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[UserListItem], tags=["users"], responses=_ERRORS)
def list_users(user: SupervisorOrManager, db: DbSession, role: UserRole | None = None,
               active_only: bool = True) -> list[UserListItem]:
    query = select(User).order_by(User.name)
    scope = access.site_scope(user)
    if scope is not None:
        query = query.where(User.site_id == scope)
    if role:
        query = query.where(User.role == role)
    if active_only:
        query = query.where(User.is_active.is_(True))
    users = list(db.scalars(query))
    open_counts = dict(db.execute(select(WorkOrder.assigned_to, func.count()).where(
        WorkOrder.assigned_to.in_([u.id for u in users]), WorkOrder.status.in_(OPEN_STATUSES))
        .group_by(WorkOrder.assigned_to)).all()) if users else {}
    return [UserListItem(id=u.id, name=u.name, email=u.email, role=u.role, preferred_language=u.preferred_language,
                         site_id=u.site_id, is_active=u.is_active, open_assigned=open_counts.get(u.id, 0))
            for u in users]


# ── checklist templates ──────────────────────────────────────────────────

def _template_out(t) -> TemplateOut:
    return TemplateOut(id=t.id, name=t.name, equipment_category=t.equipment_category,
                       work_order_type=t.work_order_type, version=t.version, is_active=t.is_active,
                       created_at=t.created_at,
                       items=[TemplateItemOut(id=i.id, sequence=i.sequence, description=i.description,
                                              is_mandatory=i.is_mandatory) for i in t.items])


@router.get("/checklists/templates", response_model=list[TemplateOut], tags=["checklists"], responses=_ERRORS)
def list_templates(_: CurrentUser, db: DbSession, category: EquipmentCategory | None = None,
                   active_only: bool = True) -> list[TemplateOut]:
    return [_template_out(t) for t in checklists.list_templates(db, category, active_only)]


@router.get("/checklists/templates/{template_id}", response_model=TemplateOut, tags=["checklists"],
            responses=_ERRORS)
def get_template(template_id: uuid.UUID, _: CurrentUser, db: DbSession) -> TemplateOut:
    return _template_out(checklists.get_template(db, template_id))


@router.post("/checklists/templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED,
             tags=["checklists"], responses=_ERRORS)
def publish_template(body: TemplateCreate, user: SupervisorOrManager, db: DbSession) -> TemplateOut:
    """Publish company-approved SOP steps as the next version; the previous version is deactivated.

    Steps are entered by supervisors. KAAMSETU never generates checklist content.
    """
    tpl = checklists.publish_template(db, user, body.name, body.equipment_category, body.work_order_type,
                                      [(i.description, i.is_mandatory) for i in body.items])
    db.commit()
    return _template_out(tpl)


@router.post("/checklists/templates/{template_id}/deactivate", response_model=TemplateOut, tags=["checklists"],
             responses=_ERRORS)
def deactivate_template(template_id: uuid.UUID, user: SupervisorOrManager, db: DbSession) -> TemplateOut:
    tpl = checklists.deactivate_template(db, user, checklists.get_template(db, template_id))
    db.commit()
    return _template_out(tpl)


# ── handovers ────────────────────────────────────────────────────────────

@router.post("/handovers", response_model=HandoverDetail, status_code=status.HTTP_201_CREATED, tags=["handovers"],
             responses=_ERRORS)
def create_handover(body: HandoverCreate, user: CurrentUser, db: DbSession) -> HandoverDetail:
    """Typed handover. The structured summary is built from work-order records plus the author's own sentences."""
    h = handovers.create(db, user, body.shift_identifier, body.notes, body.language.value if body.language else None)
    return handovers.detail(db, h)


@router.post("/handovers/voice", response_model=HandoverDetail, status_code=status.HTTP_201_CREATED,
             tags=["handovers"], responses=_ERRORS)
def create_voice_handover(
    user: CurrentUser,
    db: DbSession,
    prisma: Annotated[PrismaClient, Depends(speech.get_prisma_client)],
    shift_identifier: Annotated[str, Form(min_length=1, max_length=64)],
    audio: Annotated[UploadFile, File(description="Spoken handover notes, up to 30 s")],
    language: Annotated[LanguageCode | None, Form()] = None,
) -> HandoverDetail:
    """Spoken handover: Prisma transcript is stored verbatim as the original notes."""
    data = audio.file.read(get_settings().max_audio_upload_mb * 1024 * 1024 + 1)
    result, _ = speech.transcribe_upload(db, user, prisma, data, language.value if language else None)
    h = handovers.create(db, user, shift_identifier, result.transcript,
                         language.value if language else None, detected_language=result.detected_language,
                         transcript_meta={"gnani_request_id": result.request_id, "model": result.model,
                                          "language_requested": result.language_code_requested})
    return handovers.detail(db, h)


@router.get("/handovers", response_model=HandoverPage, tags=["handovers"], responses=_ERRORS)
def list_handovers(user: CurrentUser, db: DbSession, status_: Annotated[HandoverStatus | None,
                   Query(alias="status")] = None, page: Annotated[int, Query(ge=1)] = 1,
                   page_size: Annotated[int, Query(ge=1, le=100)] = 20) -> HandoverPage:
    return handovers.list_handovers(db, user, status_, page, page_size)


@router.get("/handovers/{handover_id}", response_model=HandoverDetail, tags=["handovers"], responses=_ERRORS)
def get_handover(handover_id: uuid.UUID, user: CurrentUser, db: DbSession) -> HandoverDetail:
    return handovers.detail(db, handovers.get(db, user, handover_id))


@router.post("/handovers/{handover_id}/review", response_model=HandoverDetail, tags=["handovers"],
             responses=_ERRORS)
def review_handover(handover_id: uuid.UUID, body: HandoverReview, user: SupervisorOrManager,
                    db: DbSession) -> HandoverDetail:
    h = handovers.review(db, user, handovers.get(db, user, handover_id), body.comment, body.pending_actions)
    return handovers.detail(db, h)


# ── dashboard ────────────────────────────────────────────────────────────

@router.get("/dashboard/overview", response_model=Overview, tags=["dashboard"], responses=_ERRORS)
def overview(user: SupervisorOrManager, db: DbSession) -> Overview:
    return dashboard.overview(db, user)


@router.get("/dashboard/work-order-trends", response_model=list[TrendPoint], tags=["dashboard"], responses=_ERRORS)
def work_order_trends(user: SupervisorOrManager, db: DbSession,
                      days: Annotated[int, Query(ge=1, le=365)] = 30) -> list[TrendPoint]:
    return dashboard.trends(db, user, days)


@router.get("/dashboard/equipment-issues", response_model=EquipmentIssues, tags=["dashboard"], responses=_ERRORS)
def equipment_issues(user: SupervisorOrManager, db: DbSession, days: Annotated[int, Query(ge=1, le=365)] = 90,
                     limit: Annotated[int, Query(ge=1, le=50)] = 10) -> EquipmentIssues:
    return dashboard.equipment_issues(db, user, days, limit)


@router.get("/dashboard/technician-workload", response_model=list[TechnicianWorkload], tags=["dashboard"],
            responses=_ERRORS)
def technician_workload(user: SupervisorOrManager, db: DbSession) -> list[TechnicianWorkload]:
    return dashboard.technician_workload(db, user)


# ── audit ────────────────────────────────────────────────────────────────

@router.get("/audit-logs", response_model=AuditPage, tags=["audit"], responses=_ERRORS)
def audit_logs(user: SupervisorOrManager, db: DbSession, entity_type: str | None = None,
               entity_id: uuid.UUID | None = None, actor_id: uuid.UUID | None = None,
               action: str | None = None, page: Annotated[int, Query(ge=1)] = 1,
               page_size: Annotated[int, Query(ge=1, le=200)] = 50) -> AuditPage:
    """Append-only audit trail (supervisors and managers). Site-scoped for users with a site."""
    query = select(AuditLog, User).outerjoin(User, User.id == AuditLog.actor_id)
    scope = access.site_scope(user)
    if scope is not None:
        # Entries by people at this site, plus automatic (system) entries on this site's work orders.
        site_users = select(User.id).where(User.site_id == scope)
        query = query.where((AuditLog.actor_id.in_(site_users)) | (AuditLog.actor_id.is_(None)))
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)
    if actor_id:
        query = query.where(AuditLog.actor_id == actor_id)
    if action:
        query = query.where(AuditLog.action == action)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(query.order_by(AuditLog.seq.desc()).offset((page - 1) * page_size)
                      .limit(page_size)).all()
    return AuditPage(items=[AuditEntry(id=a.id, action=a.action, actor=person(u), previous_value=a.previous_value,
                                       new_value=a.new_value, comment=a.comment, timestamp=a.timestamp,
                                       entity_type=a.entity_type, entity_id=a.entity_id) for a, u in rows],
                     total=total, page=page, page_size=page_size)
