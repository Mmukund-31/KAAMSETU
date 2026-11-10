"""Spoken letters and numbers -> equipment-code parts.

Prisma converts most spoken codes to digits ("M-204", "M 204"), but observed transcripts also keep
number words: Telugu "ఎం రెండు వందల నాలుగు" and auto-detected "एम टू ज़ीरो फोर", "H four hundred one".
This module turns those back into letters and digits. It never guesses: an unparseable sequence
yields nothing.
"""

from app.intelligence.text import normalize

# Spoken letter names -> letter. Kept to names that are unambiguous in maintenance speech
# (e.g. Hindi "के"/Hinglish "ke" are postpositions, so K is only recognised as a Latin letter).
LETTERS: dict[str, str] = {}
_LETTER_NAMES = {
    "A": ["a", "ए", "ఎ"],
    "B": ["b", "bee", "बी", "బి", "బీ"],
    "C": ["c", "see", "सी", "సి", "సీ"],
    "D": ["d", "dee", "डी", "డి", "డీ"],
    "E": ["e", "ee", "ई", "ఇ", "ఈ"],
    "F": ["f", "ef", "एफ", "ఎఫ్"],
    "G": ["g", "jee", "जी", "జి", "జీ"],
    "H": ["h", "aitch", "etch", "एच", "హెచ్"],
    "I": ["i", "आई", "ఐ"],
    "J": ["j", "jay", "जे", "జె"],
    "K": ["k"],
    "L": ["l", "el", "एल", "ఎల్"],
    "M": ["m", "em", "एम", "ఎం", "ఎమ్"],
    "N": ["n", "en", "एन", "ఎన్"],
    "O": ["ओ", "ఓ"],
    "P": ["p", "pee", "पी", "పి", "పీ"],
    "Q": ["q", "queue", "क्यू", "క్యూ"],
    "R": ["r", "ar", "आर", "ఆర్"],
    "S": ["s", "es", "एस", "ఎస్"],
    "T": ["t", "tee", "टी", "టి", "టీ"],
    "U": ["u", "you", "यू", "యు", "యూ"],
    "V": ["v", "vee", "वी", "వి", "వీ"],
    "W": ["w", "डब्ल्यू", "డబ్ల్యు", "డబ్ల్యూ"],
    "X": ["x", "ex", "एक्स", "ఎక్స్"],
    "Y": ["y", "why", "वाई", "వై"],
    "Z": ["z", "zed", "zee", "जेड", "ज़ेड", "జెడ్"],
}
for _letter, _names in _LETTER_NAMES.items():
    for _name in _names:
        LETTERS[normalize(_name)] = _letter

# Number words -> (value, kind). kind: unit (0-9), teen (10-19), tens (20..90), mult (100, 1000).
NUMBER_WORDS: dict[str, tuple[int, str]] = {}


def _add(kind: str, value: int, *words: str) -> None:
    for w in words:
        NUMBER_WORDS[normalize(w)] = (value, kind)


# English (also as Prisma writes them in Devanagari when auto-detecting: टू, ज़ीरो, फोर ...)
_add("unit", 0, "zero", "oh", "o", "nought", "ज़ीरो", "जीरो", "ओ")
_add("unit", 1, "one", "won", "वन")
_add("unit", 2, "two", "to", "too", "टू")
_add("unit", 3, "three", "थ्री")
_add("unit", 4, "four", "for", "फोर", "फ़ोर")
_add("unit", 5, "five", "फाइव", "फ़ाइव")
_add("unit", 6, "six", "सिक्स")
_add("unit", 7, "seven", "सेवन")
_add("unit", 8, "eight", "एट", "ऐट")
_add("unit", 9, "nine", "नाइन")
for _v, _w in enumerate(["ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
                         "seventeen", "eighteen", "nineteen"], start=10):
    _add("teen", _v, _w)
for _v, _w in zip(range(20, 100, 10), ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty",
                                       "ninety"], strict=True):
    _add("tens", _v, _w)
_add("mult", 100, "hundred", "हंड्रेड")
_add("mult", 1000, "thousand", "थाउजेंड")

# Hinglish (romanised Hindi)
_add("unit", 0, "shunya", "sifar", "sunya")
_add("unit", 1, "ek")
_add("unit", 2, "do", "doh")
_add("unit", 3, "teen", "tin")
_add("unit", 4, "char", "chaar", "chaar")
_add("unit", 5, "paanch", "panch", "paach")
_add("unit", 6, "chhe", "che", "chhah", "chheh")
_add("unit", 7, "saat", "sat")
_add("unit", 8, "aath", "aat")
_add("unit", 9, "nau")
_add("teen", 10, "das")
_add("tens", 20, "bees", "bis")
_add("tens", 30, "tees")
_add("tens", 40, "chaalis", "chalis")
_add("tens", 50, "pachaas", "pachas")
_add("tens", 70, "sattar")
_add("tens", 80, "assi")
_add("tens", 90, "nabbe")
_add("mult", 100, "sau", "so")
_add("mult", 1000, "hazaar", "hazar", "hajar")

# Hindi (Devanagari)
_add("unit", 0, "शून्य", "सिफर", "सिफ़र")
_add("unit", 1, "एक")
_add("unit", 2, "दो")
_add("unit", 3, "तीन")
_add("unit", 4, "चार")
_add("unit", 5, "पाँच", "पांच")
_add("unit", 6, "छह", "छः", "छे", "छ")
_add("unit", 7, "सात")
_add("unit", 8, "आठ")
_add("unit", 9, "नौ")
for _v, _w in enumerate(["दस", "ग्यारह", "बारह", "तेरह", "चौदह", "पंद्रह", "सोलह", "सत्रह", "अठारह", "उन्नीस"],
                        start=10):
    _add("teen", _v, _w)
for _v, _w in zip(range(20, 100, 10), ["बीस", "तीस", "चालीस", "पचास", "साठ", "सत्तर", "अस्सी", "नब्बे"],
                  strict=True):
    _add("tens", _v, _w)
_add("mult", 100, "सौ")
_add("mult", 1000, "हज़ार", "हजार")

# Telugu
_add("unit", 0, "సున్నా", "సున్న")
_add("unit", 1, "ఒకటి", "ఒక")
_add("unit", 2, "రెండు")
_add("unit", 3, "మూడు")
_add("unit", 4, "నాలుగు")
_add("unit", 5, "ఐదు", "అయిదు")
_add("unit", 6, "ఆరు")
_add("unit", 7, "ఏడు")
_add("unit", 8, "ఎనిమిది")
_add("unit", 9, "తొమ్మిది")
_add("teen", 10, "పది")
for _v, _w in zip(range(20, 100, 10), ["ఇరవై", "ముప్పై", "నలభై", "యాభై", "అరవై", "డెబ్బై", "ఎనభై", "తొంభై"],
                  strict=True):
    _add("tens", _v, _w)
_add("mult", 100, "వంద", "వందల", "వందలు", "నూట", "నూరు")
_add("mult", 1000, "వెయ్యి", "వేల")

# Telugu postpositions that attach to the last number word ("నాలుగులో" = "in four").
_TE_SUFFIXES = ("లో", "కి", "కు", "ని", "తో", "పై", "మీద")
_FILLERS = {"and", "aur", "और"}
_HYPHEN_WORDS = {"dash", "hyphen", "हाइफन", "हाइफ़न", "डैश", "హైఫన్", "డాష్"}


def number_token(tok: str) -> tuple[int, str] | None:
    if tok.isdigit():
        return int(tok), "digits"
    if tok in NUMBER_WORDS:
        return NUMBER_WORDS[tok]
    for suffix in _TE_SUFFIXES:
        if tok.endswith(suffix) and tok[: -len(suffix)] in NUMBER_WORDS:
            return NUMBER_WORDS[tok[: -len(suffix)]]
    return None


def words_to_digits(values: list[tuple[int, str]]) -> str | None:
    """Convert a run of number tokens to a digit string.

    With a multiplier ("two hundred four", "दो सौ चार", "రెండు వందల నాలుగు") the run is read as one number.
    Without one ("two zero four", "four oh one") each token contributes its digits in order.
    """
    if not values:
        return None
    if any(kind == "mult" for _, kind in values):
        total, current = 0, 0
        for value, kind in values:
            if kind == "mult":
                if value >= 1000:
                    total += (current or 1) * value
                    current = 0
                else:
                    current = (current or 1) * value
            elif kind == "digits":
                return None  # mixing digits and multipliers is not a code we can read safely
            else:
                current += value
        return str(total + current)
    out, i = "", 0
    while i < len(values):
        value, kind = values[i]
        if kind == "tens" and i + 1 < len(values) and values[i + 1][1] == "unit" and values[i + 1][0] > 0:
            out += str(value + values[i + 1][0])
            i += 2
            continue
        out += str(value)
        i += 1
    return out


def spoken_codes(text: str) -> list[tuple[str, str, str]]:
    """Find spoken codes: letter name followed by number words/digits.

    Returns (letters, digits, heard_text) tuples, e.g. ("M", "204", "ఎం రెండు వందల నాలుగు").
    """
    toks = normalize(text).split()
    found = []
    i = 0
    while i < len(toks):
        letter = LETTERS.get(toks[i])
        if letter is None:
            i += 1
            continue
        j = i + 1
        if j < len(toks) and toks[j] in _HYPHEN_WORDS:
            j += 1
        values = []
        while j < len(toks):
            parsed = number_token(toks[j])
            if parsed is None and toks[j] in _FILLERS and values and j + 1 < len(toks) \
                    and number_token(toks[j + 1]) is not None:
                j += 1  # "two hundred and four"
                continue
            if parsed is None:
                break
            values.append(parsed)
            j += 1
        digits = words_to_digits(values) if values and not all(k == "digits" for _, k in values) else None
        if digits is None and values and all(k == "digits" for _, k in values):
            digits = "".join(str(v) for v, _ in values)
        if digits and 2 <= len(digits) <= 4:
            found.append((letter, digits, " ".join(toks[i:j])))
            i = j
        else:
            i += 1
    return found
