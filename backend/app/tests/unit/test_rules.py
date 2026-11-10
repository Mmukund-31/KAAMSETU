"""Classification, prioritisation, missing fields, drafting and response templates."""

import pytest

from app.domain.enums import EquipmentCategory as Cat
from app.domain.enums import Priority, ProductionImpact
from app.intelligence.classification import classify
from app.intelligence.config_loader import priority_rules, responses, taxonomy
from app.intelligence.drafting import draft_from_report, merge_answer
from app.intelligence.extraction import extract
from app.intelligence.missing_fields import find_missing
from app.intelligence.models import PriorityContext, ReportDraft
from app.intelligence.prioritization import prioritize
from app.intelligence.response import placeholders, priority_label, render

# ── classification ───────────────────────────────────────────────────────


def test_demo_report_is_mechanical():
    c = classify(["bearing_vibration", "abnormal_pressure"], Cat.MECHANICAL)
    assert c.category == Cat.MECHANICAL and c.basis == "symptoms"
    assert c.scores == {"mechanical": 3.5, "hydraulic": 1.0}


def test_generic_symptom_follows_equipment_category():
    assert classify(["abnormal_pressure"], Cat.HYDRAULIC).category == Cat.HYDRAULIC
    assert classify(["abnormal_pressure"], Cat.MECHANICAL).category == Cat.MECHANICAL  # 1.5 beats 1.0


def test_specific_symptom_beats_equipment_category():
    assert classify(["tripping"], Cat.MECHANICAL).category == Cat.ELECTRICAL  # 2.0 vs 1.5


def test_no_symptoms_uses_equipment_then_other():
    assert classify([], Cat.PNEUMATIC).model_dump(include={"category", "basis"}) == \
        {"category": Cat.PNEUMATIC, "basis": "equipment"}
    assert classify([], None).model_dump(include={"category", "basis"}) == {"category": Cat.OTHER, "basis": "none"}


def test_override_wins():
    assert classify(["tripping"], Cat.ELECTRICAL, override=Cat.INSTRUMENTATION).basis == "override"


# ── prioritisation (every rule) ──────────────────────────────────────────

def ctx(**kw) -> PriorityContext:
    base = dict(safety_concern=False, production_impact=ProductionImpact.RUNNING, equipment_critical=False,
                symptom_severities=["medium"], category=Cat.MECHANICAL)
    base.update(kw)
    return PriorityContext(**base)


@pytest.mark.parametrize("kwargs, level, rule", [
    (dict(safety_concern=True, production_impact=ProductionImpact.RUNNING), Priority.CRITICAL, "safety_reported"),
    (dict(production_impact=ProductionImpact.STOPPED, equipment_critical=True), Priority.CRITICAL,
     "critical_equipment_stopped"),
    (dict(production_impact=ProductionImpact.STOPPED), Priority.HIGH, "production_stopped"),
    (dict(production_impact=ProductionImpact.DEGRADED), Priority.HIGH, "production_degraded"),
    (dict(symptom_severities=["low", "high"]), Priority.HIGH, "high_severity_symptom"),
    (dict(equipment_critical=True), Priority.HIGH, "critical_equipment_fault"),
    (dict(), Priority.MEDIUM, "fault_reported"),
    (dict(symptom_severities=[]), Priority.LOW, "observation"),
])
def test_priority_rules(kwargs, level, rule):
    d = prioritize(ctx(**kwargs))
    assert (d.level, d.rule_id) == (level, rule)
    assert d.explanation


def test_demo_priority_is_high_because_m204_is_critical():
    d = prioritize(ctx(equipment_critical=True, symptom_severities=["medium", "medium"]))
    assert (d.level, d.rule_id, d.provisional) == (Priority.HIGH, "critical_equipment_fault", False)


def test_unknown_production_or_equipment_marks_priority_provisional():
    assert prioritize(ctx(production_impact=ProductionImpact.UNKNOWN)).provisional
    assert prioritize(ctx(equipment_critical=None)).provisional


def test_every_rule_is_reachable():
    ids = [r.id for r in priority_rules().rules]
    assert ids[-1] == "observation" and len(ids) == len(set(ids))


# ── missing fields ───────────────────────────────────────────────────────

def test_missing_fields_in_policy_order():
    m = find_missing(ReportDraft(), "missing")
    assert [f.field for f in m] == ["equipment_code", "symptoms", "production_impact"]
    assert m[0].reason == "not_stated"


def test_unknown_equipment_reason():
    assert find_missing(ReportDraft(), "unknown")[0].reason == "not_registered"


def test_complete_draft_has_nothing_missing():
    d = ReportDraft(equipment_code="M-204", symptoms=["vibration"], production_impact=ProductionImpact.RUNNING)
    assert find_missing(d, "matched") == []


def test_description_accepted_after_symptom_question_answered():
    d = ReportDraft(equipment_code="M-204", issue_description="Guard is loose and rattling",
                    production_impact=ProductionImpact.RUNNING)
    assert [f.field for f in find_missing(d, "matched")] == ["symptoms"]
    assert find_missing(d, "matched", answered_fields={"symptoms"}) == []


# ── drafting ─────────────────────────────────────────────────────────────

def test_draft_from_report_uses_technicians_own_words():
    text = "M-204 mein vibration aa raha hai"
    d = draft_from_report(extract(text, "hinglish"))
    assert d.issue_description == text
    assert (d.equipment_code, d.symptoms, d.production_impact) == ("M-204", ["vibration"], ProductionImpact.UNKNOWN)


@pytest.mark.parametrize("answer, expected", [
    ("Haan, production chal raha hai", ProductionImpact.RUNNING),
    ("haan", ProductionImpact.RUNNING),
    ("nahi, ruk gaya hai", ProductionImpact.STOPPED),
    ("nahi", ProductionImpact.STOPPED),
    ("dheere chal raha hai", ProductionImpact.DEGRADED),
])
def test_merge_production_answer(answer, expected):
    d = ReportDraft(equipment_code="M-204", symptoms=["vibration"])
    merged = merge_answer(d, extract(answer, "hinglish", focus="production_impact"), "production_impact")
    assert merged.production_impact == expected


def test_merge_does_not_overwrite_other_confirmed_fields():
    d = ReportDraft(equipment_code="M-204", symptoms=["vibration"], production_impact=ProductionImpact.RUNNING)
    merged = merge_answer(d, extract("H-401 mein oil leak, production ruk gaya", "hinglish"), "symptoms")
    assert merged.equipment_code == "M-204"                       # not the asked field: kept
    assert merged.production_impact == ProductionImpact.RUNNING     # not the asked field: kept
    assert merged.symptoms == ["vibration", "oil_leak"]             # new information is added


def test_merge_equipment_answer_replaces_code():
    d = ReportDraft(equipment_code="M-209", symptoms=["vibration"])
    assert merge_answer(d, extract("M-204", "en", focus="equipment_code"), "equipment_code").equipment_code == "M-204"


def test_merge_never_clears_safety():
    d = ReportDraft(safety_concern=True)
    assert merge_answer(d, extract("sab theek hai", "hinglish"), "symptoms").safety_concern


# ── response templates ───────────────────────────────────────────────────

LANGS = ["en", "hinglish", "hi", "te"]


@pytest.mark.parametrize("key", list(responses().messages))
def test_templates_use_same_placeholders_in_every_language(key):
    sets = {lang: placeholders(responses().messages[key][lang]) for lang in LANGS}
    assert len({frozenset(s) for s in sets.values()}) == 1, sets


@pytest.mark.parametrize("lang", LANGS)
def test_every_template_renders(lang):
    for key in responses().messages:
        text = render(key, lang, code="M-204", heard="M-209", number="WO-1001",
                      priority=priority_label(Priority.HIGH, lang))
        assert "{" not in text and text.strip()


def test_spec_example_follow_up_question_in_hinglish():
    assert render("ask_production_impact", "hinglish", code="M-204") == \
        "M-204 ke liye maintenance request bana raha hoon. Kya production abhi bhi chal raha hai?"


def test_missing_placeholder_is_an_error_not_silent():
    with pytest.raises(KeyError):
        render("confirm_preview", "en", code="M-204")


# ── configuration integrity ──────────────────────────────────────────────

def test_every_symptom_has_labels_and_valid_suppression():
    tax = taxonomy()
    for key, sym in tax.symptoms.items():
        assert {"en", "hi", "te"} <= set(sym.label), key
        assert key not in sym.suppressed_by


def test_safety_symptoms_are_high_severity():
    assert all(s.severity == "high" for s in taxonomy().symptoms.values() if s.safety)
