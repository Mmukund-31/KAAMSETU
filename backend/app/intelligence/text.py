"""Text normalisation, clause splitting, keyword matching and negation scope.

Works on English, Hinglish (Latin script), Hindi (Devanagari) and Telugu text. Python's \\b is
unreliable for Indic scripts (vowel signs are not word characters), so matching is done on
whitespace tokens instead of regex word boundaries.
"""

import re
import unicodedata
from dataclasses import dataclass

_NUKTA = "़"
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍﻿"), None)
_PUNCT = re.compile(r"[,.;:!?।॥\"'`()\[\]{}<>/\\|*+=~_#@&%$^\-–—‘’“”]+")
_SPACES = re.compile(r"\s+")

# Clause boundaries: punctuation (incl. the Devanagari danda) and coordinating conjunctions.
_CONJUNCTIONS = {
    "and", "but", "though", "however", "aur", "lekin", "magar", "parantu", "kintu",
    "और", "लेकिन", "मगर", "परंतु", "किंतु", "మరియు", "కానీ", "కాని", "అయితే",
}

# Negators that come BEFORE what they negate ("no smoke", "not vibrating").
_NEG_BEFORE = {"no", "not", "never", "without", "none", "बिना", "dont", "doesnt", "isnt", "arent", "cant"}
# Negators that come AFTER (Hindi, Hinglish, Telugu verb-final order: "leak nahi hai", "పొగ లేదు").
_NEG_AFTER = {"nahi", "nahin", "nhi", "nai", "na", "नहीं", "नही", "ना", "లేదు", "లేవు", "కాదు", "లేను"}
_NEG_AFTER_SUFFIXES = ("లేదు", "ట్లేదు", "లేవు")
NEG_WINDOW_BEFORE = 2
NEG_WINDOW_AFTER = 3


def normalize(text: str) -> str:
    """Lower-case, NFC, drop nukta and zero-width characters, punctuation to spaces."""
    t = unicodedata.normalize("NFC", text).translate(_ZERO_WIDTH).replace(_NUKTA, "")
    t = _PUNCT.sub(" ", t.lower())
    return _SPACES.sub(" ", t).strip()


def tokens(text: str) -> list[str]:
    return normalize(text).split()


_SENTENCE_PUNCT = re.compile(r"[.!?।॥\n]+")
_INNER_PUNCT = re.compile(r"[,;:]+")


def _split_conjunctions(chunk: str) -> list[list[str]]:
    result: list[list[str]] = []
    current: list[str] = []
    for tok in tokens(chunk):
        if tok in _CONJUNCTIONS:
            if current:
                result.append(current)
            current = []
        else:
            current.append(tok)
    if current:
        result.append(current)
    return result


def sentence_clauses(text: str) -> list[list[list[str]]]:
    """Sentences, each a list of clauses (token lists). Lets a subject carry over within one sentence."""
    out = []
    for sentence in _SENTENCE_PUNCT.split(unicodedata.normalize("NFC", text)):
        clause_list = [c for part in _INNER_PUNCT.split(sentence) for c in _split_conjunctions(part)]
        if clause_list:
            out.append(clause_list)
    return out


def clauses(text: str) -> list[list[str]]:
    """Split into clauses (token lists) at punctuation and conjunctions."""
    return [c for sentence in sentence_clauses(text) for c in sentence]


@dataclass(frozen=True)
class Keyword:
    """A keyword phrase. A leading '=' requires exact token equality; otherwise each token is a prefix (stem)."""

    raw: str
    parts: tuple[str, ...]
    exact: bool

    @classmethod
    def parse(cls, raw: str) -> "Keyword":
        exact = raw.startswith("=")
        parts = tuple(tokens(raw[1:] if exact else raw))
        if not parts:
            raise ValueError(f"Empty keyword: {raw!r}")
        return cls(raw=raw, parts=parts, exact=exact)

    def find(self, toks: list[str]) -> list[int]:
        """Start indices where this keyword matches the token list."""
        n = len(self.parts)
        hits = []
        for i in range(len(toks) - n + 1):
            window = toks[i:i + n]
            if self.exact:
                ok = all(w == p for w, p in zip(window, self.parts, strict=True))
            else:
                # Every token but the last must match exactly; the last is a stem (handles inflection).
                ok = all(w == p for w, p in zip(window[:-1], self.parts[:-1], strict=True)) and window[-1].startswith(
                    self.parts[-1]
                )
            if ok:
                hits.append(i)
        return hits


def is_negated(toks: list[str], start: int, length: int) -> bool:
    """True if a negator governs the phrase at toks[start:start+length] within the same clause."""
    before = toks[max(0, start - NEG_WINDOW_BEFORE):start]
    after = toks[start + length:start + length + NEG_WINDOW_AFTER]
    if any(t in _NEG_BEFORE for t in before):
        return True
    return any(t in _NEG_AFTER or t.endswith(_NEG_AFTER_SUFFIXES) for t in after)


YES_WORDS = {"yes", "yeah", "yep", "haan", "han", "haa", "ha", "ji", "hanji", "haanji", "हाँ", "हां", "हा", "जी",
             "హా", "అవును", "ఔను", "అవునండి", "అవును అండి", "sure", "correct", "right"}
NO_WORDS = {"no", "nope", "nahi", "nahin", "nhi", "na", "नहीं", "नही", "ना", "లేదు", "కాదు", "లేదండి"}


def yes_no(text: str) -> str | None:
    """Detect a leading yes/no answer ("Haan, ...", "No, ..."). Returns 'yes', 'no' or None."""
    for tok in tokens(text)[:3]:
        if tok in YES_WORDS:
            return "yes"
        if tok in NO_WORDS:
            return "no"
    return None
