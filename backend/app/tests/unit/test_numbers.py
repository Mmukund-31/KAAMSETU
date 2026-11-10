import pytest

from app.intelligence.numbers import spoken_codes, words_to_digits
from app.intelligence.text import normalize


def digits(words: str) -> str | None:
    from app.intelligence.numbers import number_token

    return words_to_digits([number_token(t) for t in normalize(words).split()])


@pytest.mark.parametrize("words, expected", [
    ("two zero four", "204"), ("two oh four", "204"), ("two hundred four", "204"), ("four hundred one", "401"),
    ("four oh one", "401"), ("twenty four", "24"), ("one twenty", "120"), ("one one zero", "110"),
    ("दो सौ चार", "204"), ("चार सौ एक", "401"), ("एक सौ दस", "110"), ("टू जीरो फोर", "204"),
    ("do sau chaar", "204"), ("ek ek shunya", "110"),
    ("రెండు వందల నాలుగు", "204"), ("నాలుగు సున్నా ఒకటి", "401"), ("నూట పది", "110"), ("నాలుగులో", "4"),
])
def test_words_to_digits(words, expected):
    assert digits(words) == expected


@pytest.mark.parametrize("text, expected", [
    ("machine em two zero four", [("M", "204")]),
    ("machine M two hundred and four", [("M", "204")]),
    ("H four hundred one has a leak", [("H", "401")]),
    ("मशीन एम दो सौ चार में", [("M", "204")]),
    ("मशीन नंबर एम टू ज़ीरो फोर है", [("M", "204")]),
    ("మెషిన్ ఎం రెండు వందల నాలుగు లో", [("M", "204")]),
    ("మెషిన్ హెచ్ నాలుగు సున్నా ఒకటి లో", [("H", "401")]),
    ("E 1 1 0 panel", [("E", "110")]),
    ("e dash one one zero", [("E", "110")]),
])
def test_spoken_codes(text, expected):
    assert [(letters, d) for letters, d, _ in spoken_codes(text)] == expected


@pytest.mark.parametrize("text", [
    "i have two problems",          # one digit is not a code
    "a for apple",
    "ke do saal",                   # Hindi postposition "ke" is not the letter K
    "machine is fine",
])
def test_no_false_codes(text):
    assert spoken_codes(text) == []
