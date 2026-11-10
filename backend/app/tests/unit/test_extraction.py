from collections import Counter

import pytest

from app.intelligence.extraction import extract
from app.tests.unit.extraction_cases import CASES


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_extraction_case(case):
    r = extract(case["text"], case["lang"])
    assert [c.display for c in r.equipment_candidates][: len(case["codes"])] == case["codes"], \
        [c.model_dump() for c in r.equipment_candidates]
    if not case["codes"]:
        assert r.equipment_candidates == []
    assert {s.key for s in r.symptoms} == case["symptoms"]
    assert (r.production_impact.value if r.production_impact else None) == case["impact"]
    assert r.safety_concern is case["safety"]
    assert case.get("negated", set()) <= set(r.negated_symptoms)
    if "location" in case:
        assert r.location_note == case["location"]


def test_case_set_covers_every_language_evenly():
    counts = Counter(c["lang"] for c in CASES)
    assert set(counts) == {"en", "hinglish", "hi", "te"}
    assert min(counts.values()) >= 8
    assert len(CASES) >= 40


def test_extraction_keeps_source_terms_for_explainability():
    r = extract("bearing mein vibration aa raha hai", "hinglish")
    assert r.symptoms[0].terms == ["bearing", "vibration"]


def test_candidate_methods_and_confidence():
    direct = extract("Machine M-204 is noisy", "en").equipment_candidates[0]
    spoken = extract("Machine em two zero four is noisy", "en").equipment_candidates[0]
    digits = extract("Machine number 204 is noisy", "en").equipment_candidates[0]
    assert (direct.method, direct.confidence) == ("direct", "high")
    assert (spoken.method, spoken.confidence) == ("spoken", "medium")
    assert (digits.method, digits.confidence) == ("digits_only", "low")


@pytest.mark.parametrize("text", [
    "Machine no 204 is noisy",        # "NO" is not an equipment prefix
    "Pressure is at 120 psi",          # units are not prefixes
    "Running at 1500 rpm",
])
def test_common_words_are_not_equipment_prefixes(text):
    codes = [c.code for c in extract(text, "en").equipment_candidates]
    assert not any(code.startswith(("NO", "AT", "RPM", "PSI")) for code in codes)


def test_symptom_requires_both_keyword_groups_in_same_clause():
    # "pressure" and "high" are in different clauses: not an abnormal pressure report.
    r = extract("Pressure gauge was replaced yesterday. Noise level is high.", "en")
    assert "abnormal_pressure" not in {s.key for s in r.symptoms}


def test_negation_scope_does_not_leak_to_next_symptom():
    r = extract("koi leak nahi sirf awaaz aa rahi hai", "hinglish")
    assert {s.key for s in r.symptoms} == {"abnormal_noise"}
    assert "leak" in r.negated_symptoms


@pytest.mark.parametrize("text, impact", [
    ("production pehle ruk gaya tha, ab chal raha hai", "running"),   # last mention wins
    ("machine chal rahi thi, phir ruk gayi", "stopped"),
    ("production chal raha hai lekin slow hai", "degraded"),          # running, but slow
])
def test_impact_subject_carries_over_and_last_mention_wins(text, impact):
    assert extract(text, "hinglish").production_impact.value == impact


def test_subject_does_not_carry_across_sentences():
    # The second sentence has no subject of its own, so "chal raha hai" there is not about production.
    r = extract("Production ruk gaya hai. Pankha chal raha hai.", "hinglish")
    assert r.production_impact.value == "stopped"


def test_short_answer_needs_focus_to_count_as_impact():
    assert extract("haan, chal raha hai", "hinglish").production_impact is None
    focused = extract("haan, chal raha hai", "hinglish", focus="production_impact")
    assert focused.production_impact.value == "running"
    assert focused.answer == "yes"


@pytest.mark.parametrize("text, answer", [
    ("Haan", "yes"), ("haan ji", "yes"), ("हाँ", "yes"), ("అవును", "yes"), ("Yes it is", "yes"),
    ("nahi", "no"), ("नहीं", "no"), ("లేదు", "no"), ("No", "no"), ("production chal raha hai", None),
])
def test_yes_no_answers(text, answer):
    assert extract(text, "hinglish").answer == answer


def test_unknown_text_yields_nothing_invented():
    r = extract("kal ki meeting ke baare mein", "hinglish")
    assert r.equipment_candidates == [] and r.symptoms == [] and r.production_impact is None
    assert r.safety_concern is False
