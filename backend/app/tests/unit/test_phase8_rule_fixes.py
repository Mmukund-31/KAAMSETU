"""Regression tests for the rule gaps found by the Phase 8 held-out evaluation (evaluation/RESULTS.md).

Each case is a phrasing the v1 held-out set showed was missed, plus a guard that the fix is not too broad.
"""

import pytest

from app.intelligence.extraction import extract


def keys(result):
    return sorted(s.key for s in result.symptoms)


def codes(result):
    return [c.code for c in result.equipment_candidates]


@pytest.mark.parametrize("text, language, expected", [
    ("the whole bay has no power", "en", ["power_failure"]),
    ("Packaging line keeps jamming at the sealing station", "en", ["jam_stuck"]),
    ("M-101 lathe start hi nahi ho raha", "hinglish", ["not_starting"]),
    ("compressor chal hi nahi raha", "hinglish", ["not_starting"]),
    ("क्लैंप लाइन में हवा का रिसाव है", "hi", ["air_leak"]),
    ("बेल्ट ढीली हो गई है", "hi", ["belt_issue"]),
    ("స్టార్టర్ దగ్గర నిప్పు రవ్వలు వస్తున్నాయి", "te", ["sparking"]),
])
def test_missed_phrasings_are_recognised(text, language, expected):
    assert keys(extract(text, language)) == expected


def test_no_power_needs_the_phrase_not_any_no():
    assert keys(extract("There is no smoke and the power supply is normal.", "en")) == []


@pytest.mark.parametrize("text, language, impact", [
    ("The boiler is still running.", "en", "running"),
    ("बॉयलर चल रहा है।", "hi", "running"),
    ("బాయిలర్ నడుస్తోంది.", "te", "running"),
    ("Production ruka hua hai.", "hinglish", "stopped"),
])
def test_machine_types_and_ruka_hua_give_production_impact(text, language, impact):
    result = extract(text, language)
    assert result.production_impact is not None and result.production_impact.value == impact


@pytest.mark.parametrize("text, language", [
    ("Machine number 1-01, the lathe spindle, is overheating", "en"),  # Prisma's formatting of a spoken 101
    ("मशीन नंबर एक सौ एक की बेल्ट ढीली है", "hi"),
    ("మెషిన్ నంబర్ నూట ఒకటి స్టార్ట్ అవ్వడం లేదు", "te"),
    ("machine number one zero one", "en"),
])
def test_spoken_numbers_after_a_number_cue(text, language):
    assert "101" in codes(extract(text, language))


def test_mixed_digits_and_number_words_are_not_read():
    assert codes(extract("number 2 sau wala", "hinglish")) == []


@pytest.mark.parametrize("text, language", [
    ("E-220 starter mein se chingari nikli", "hinglish"),  # v2 held-out miss: safety concern was not raised
    ("panel se chingaariyan aa rahi hain", "hinglish"),
    ("पैनल से चिंगारियाँ निकल रही हैं", "hi"),
])
def test_sparks_in_hinglish_and_hindi_plural_raise_safety(text, language):
    result = extract(text, language)
    assert "sparking" in keys(result)
    assert result.safety_concern is True


def test_injury_in_hinglish_raises_safety():
    result = extract("ek operator ghayal ho gaya hai", "hinglish")
    assert "injury" in keys(result) and result.safety_concern is True
