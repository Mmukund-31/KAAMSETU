"""Report orchestrator: transcript -> validated work-order preview.

Order of operations (each step deterministic and recorded in the outcome):
  1. extract what the utterance says                     (intelligence.extraction)
  2. build or update the draft                           (intelligence.drafting)
  3. resolve the equipment code against the register     (this module; registry is the only source of truth)
  4. classify, prioritise, find missing fields           (intelligence.*)
  5. decide the next action and the response text        (intelligence.response)
  6. optionally speak the response with Timbre           (services.speech; failure falls back to text)

Nothing is written to the database here. The work order is created only after the technician
confirms (Phase 4), and that step re-validates everything server-side.
"""

import base64
import difflib
import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, Unprocessable
from app.domain.enums import LanguageCode, OperationalStatus
from app.gnani.prisma import PrismaClient
from app.gnani.timbre import TimbreClient
from app.intelligence.classification import classify
from app.intelligence.config_loader import taxonomy, workflow_policy
from app.intelligence.drafting import draft_from_report, merge_answer
from app.intelligence.extraction import extract
from app.intelligence.missing_fields import find_missing
from app.intelligence.models import (
    EquipmentCandidate,
    ExtractedReport,
    PriorityContext,
    ReportDraft,
)
from app.intelligence.prioritization import prioritize
from app.intelligence.response import priority_label, render
from app.intelligence.text import tokens
from app.models import Equipment, User, normalize_equipment_code
from app.schemas.report import (
    CategoryOut,
    EquipmentBrief,
    EquipmentResolution,
    FollowUpQuestion,
    MissingFieldOut,
    ReportOutcome,
    SpokenResponse,
    SymptomOut,
)
from app.services import speech
from app.workflows import evidence as ev

logger = logging.getLogger("kaamsetu.orchestrator")

MAX_SUGGESTIONS = 5
_DETECTED_TO_UI = {"hi-IN": "hi", "te-IN": "te", "en-IN": "en"}


# ── equipment resolution ─────────────────────────────────────────────────

def _site_equipment(db: Session, user: User) -> list[Equipment]:
    query = select(Equipment).order_by(Equipment.equipment_code)
    if user.site_id is not None:
        query = query.where(Equipment.site_id == user.site_id)
    return list(db.scalars(query))


def _match(code: str, registry: list[Equipment]) -> Equipment | None:
    norm = normalize_equipment_code(code)
    if not norm:
        return None
    exact = [e for e in registry if e.code_normalized == norm]
    if exact:
        return exact[0]
    if norm.isdigit():  # digits only: accept only if exactly one registered code has these digits
        by_digits = [e for e in registry if re.fullmatch(rf"[A-Z]+{norm}", e.code_normalized)]
        if len(by_digits) == 1:
            return by_digits[0]
    return None


def _suggest(heard: str | None, text: str, registry: list[Equipment]) -> list[Equipment]:
    """Real registered machines that resemble the heard code or are named in the transcript."""
    words = {t for t in tokens(text) if len(t) > 3}
    norm = normalize_equipment_code(heard) if heard else ""
    scored = []
    for e in registry:
        score = difflib.SequenceMatcher(None, norm, e.code_normalized).ratio() if norm else 0.0
        if words & {t for t in tokens(e.name) if len(t) > 3}:
            score += 0.6
        if score >= 0.5:
            scored.append((score, e.equipment_code, e))
    scored.sort(key=lambda s: (-s[0], s[1]))
    return [e for _, _, e in scored[:MAX_SUGGESTIONS]]


def _brief(e: Equipment) -> EquipmentBrief:
    return EquipmentBrief(id=e.id, code=e.equipment_code, name=e.name, category=e.category, location=e.location,
                          is_critical=e.is_critical, operational_status=e.operational_status)


def _resolve(draft: ReportDraft, candidates: list[EquipmentCandidate], text: str,
             registry: list[Equipment]) -> tuple[Equipment | None, EquipmentResolution]:
    tried: list[str] = []
    for code in [draft.equipment_code, *[c.display for c in candidates]]:
        if not code or code in tried:
            continue
        tried.append(code)
        found = _match(code, registry)
        if found:
            return found, EquipmentResolution(status="matched", heard=code, equipment=_brief(found))
    heard = tried[0] if tried else None
    status = "unknown" if heard else "missing"
    return None, EquipmentResolution(status=status, heard=heard,
                                     suggestions=[_brief(e) for e in _suggest(heard, text, registry)])


# ── evaluation ───────────────────────────────────────────────────────────

def evaluate(
    db: Session,
    user: User,
    draft: ReportDraft,
    evidence: ev.Evidence,
    language: str,
    candidates: list[EquipmentCandidate] | None = None,
    extraction: ExtractedReport | None = None,
) -> ReportOutcome:
    tax = taxonomy()
    warnings: list[str] = []

    unknown_symptoms = [s for s in draft.symptoms if s not in tax.symptoms]
    if unknown_symptoms:
        warnings.append("unknown_symptoms_ignored")
        draft = draft.model_copy(update={"symptoms": [s for s in draft.symptoms if s in tax.symptoms]})
    # A safety concern is never cleared by the system once any recognised safety symptom is present.
    if any(tax.symptoms[s].safety for s in draft.symptoms) and not draft.safety_concern:
        draft = draft.model_copy(update={"safety_concern": True})

    registry = _site_equipment(db, user)
    equipment, resolution = _resolve(draft, candidates or [], evidence.report_text, registry)
    if equipment is not None:
        draft = draft.model_copy(update={"equipment_code": equipment.equipment_code})
        if equipment.operational_status == OperationalStatus.DECOMMISSIONED:
            warnings.append("equipment_decommissioned")

    classification = classify(draft.symptoms, equipment.category if equipment else None, draft.category_override)
    priority = prioritize(PriorityContext(
        safety_concern=draft.safety_concern,
        production_impact=draft.production_impact,
        equipment_critical=equipment.is_critical if equipment else None,
        symptom_severities=[tax.symptoms[s].severity for s in draft.symptoms],
        category=classification.category,
    ))

    missing = find_missing(draft, resolution.status, evidence.answered_fields)
    code = equipment.equipment_code if equipment else (resolution.heard or "")
    questions = {
        "equipment_code": render("equipment_unknown", language, heard=resolution.heard)
        if resolution.status == "unknown" else render("ask_equipment", language),
        "symptoms": render("ask_symptoms", language, code=code),
        "production_impact": render("ask_production_impact", language, code=code),
    }
    missing_out = [MissingFieldOut(field=m.field, reason=m.reason, question=questions[m.field]) for m in missing]

    if resolution.status == "unknown":
        next_action = "fix_equipment"
    elif missing:
        next_action = "ask_follow_up"
    else:
        next_action = "confirm_preview"
    follow_up = FollowUpQuestion(field=missing[0].field, question=missing_out[0].question) if missing else None

    if next_action == "confirm_preview":
        text = render("confirm_preview", language, code=code, priority=priority_label(priority.level, language))
    else:
        text = follow_up.question  # type: ignore[union-attr]
    if draft.safety_concern:
        text = f"{render('safety_warning', language)} {text}"

    return ReportOutcome(
        report_id=evidence.report_id,
        language=language,
        next_action=next_action,
        transcript=evidence.utterances[-1].text,
        original_transcript=evidence.original.text,
        utterances=[u.model_dump(mode="json") for u in evidence.utterances],
        draft=draft,
        equipment=resolution,
        symptoms=[SymptomOut(key=s, label=tax.symptoms[s].label_for(language), category=tax.symptoms[s].category,
                             severity=tax.symptoms[s].severity, safety=tax.symptoms[s].safety) for s in draft.symptoms],
        category=CategoryOut(value=classification.category, basis=classification.basis,
                             label=tax.category_label(classification.category, language)),
        priority=priority,
        missing_fields=missing_out,
        follow_up=follow_up,
        requires_approval=user.role in workflow_policy().approval_required_for_roles,
        warnings=warnings,
        extraction=extraction,
        response=SpokenResponse(text=text),
        evidence_token=ev.sign(evidence),
    )


def _speak(outcome: ReportOutcome, timbre: TimbreClient | None) -> ReportOutcome:
    if timbre is None:
        return outcome
    try:
        result = speech.synthesize(timbre, outcome.response.text[:500], outcome.language, None)
    except AppError as exc:
        # Spoken output is a convenience: the text response is always shown, so the flow continues.
        logger.info("TTS unavailable for report response", extra={"ctx": {"code": exc.code}})
        outcome.response.tts_available = False
        outcome.response.tts_error = exc.code
        return outcome
    outcome.response.audio_base64 = base64.b64encode(result.audio).decode("ascii")
    outcome.response.content_type = result.content_type
    outcome.response.voice = result.voice
    outcome.response.gnani_request_id = result.request_id
    outcome.response.tts_available = True
    return outcome


def _ui_language(requested: str | None, user: User, detected: str | None = None) -> str:
    if requested and requested != "auto":
        return requested
    if requested == "auto" and detected in _DETECTED_TO_UI:
        return _DETECTED_TO_UI[detected]
    return user.preferred_language.value if user.preferred_language else LanguageCode.EN.value


# ── entry points used by the API ─────────────────────────────────────────

def process_voice(db: Session, user: User, prisma: PrismaClient, timbre: TimbreClient | None, audio: bytes,
                  language: str | None) -> ReportOutcome:
    result, _ = speech.transcribe_upload(db, user, prisma, audio, language)
    lang = _ui_language(language, user, result.detected_language)
    utterance = ev.new_utterance("voice", result.transcript, gnani_request_id=result.request_id, model=result.model,
                                 language_requested=result.language_code_requested,
                                 detected_language=result.detected_language)
    report = extract(result.transcript, lang)
    outcome = evaluate(db, user, draft_from_report(report), ev.start(user.id, lang, utterance), lang,
                       report.equipment_candidates, report)
    return _speak(outcome, timbre)


def process_text(db: Session, user: User, timbre: TimbreClient | None, text: str, language: str | None,
                 evidence_token: str | None) -> ReportOutcome:
    """Typed report (voice fallback), or a correction of the transcript when evidence_token is given."""
    if evidence_token:
        evidence = ev.verify(evidence_token, user.id)
        lang = language or evidence.language
        evidence = evidence.with_utterance(ev.new_utterance("correction", text))
    else:
        lang = _ui_language(language, user)
        evidence = ev.start(user.id, lang, ev.new_utterance("text", text))
    report = extract(text, lang)
    outcome = evaluate(db, user, draft_from_report(report), evidence, lang, report.equipment_candidates, report)
    return _speak(outcome, timbre)


def follow_up(db: Session, user: User, prisma: PrismaClient | None, timbre: TimbreClient | None,
              evidence_token: str, draft: ReportDraft, field: str, answer_text: str | None,
              audio: bytes | None) -> ReportOutcome:
    evidence = ev.verify(evidence_token, user.id)
    lang = evidence.language
    if audio:
        if prisma is None:  # pragma: no cover - the API always supplies a client
            raise Unprocessable("Voice answers are not available", code="speech_not_configured")
        result, _ = speech.transcribe_upload(db, user, prisma, audio, lang)
        utterance = ev.new_utterance("follow_up_voice", result.transcript, field=field,
                                     gnani_request_id=result.request_id, model=result.model,
                                     language_requested=result.language_code_requested,
                                     detected_language=result.detected_language)
    elif answer_text and answer_text.strip():
        utterance = ev.new_utterance("follow_up_text", answer_text, field=field)
    else:
        raise Unprocessable("Please give an answer by voice or text.", code="empty_answer")

    evidence = evidence.with_utterance(utterance)
    answer = extract(utterance.text, lang, focus=field)
    merged = merge_answer(draft, answer, field)
    outcome = evaluate(db, user, merged, evidence, lang, answer.equipment_candidates, answer)
    return _speak(outcome, timbre)


def evaluate_draft(db: Session, user: User, timbre: TimbreClient | None, evidence_token: str,
                   draft: ReportDraft) -> ReportOutcome:
    """Re-check a draft after manual edits in the preview (e.g. machine picked from the list)."""
    evidence = ev.verify(evidence_token, user.id)
    outcome = evaluate(db, user, draft, evidence, evidence.language)
    return _speak(outcome, timbre)
