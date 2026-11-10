"""Transcript -> ExtractedReport.

Deterministic and explainable: every extracted value points back to the words that produced it.
Nothing is inferred beyond what was said. Equipment codes found here are only *candidates*; the
workflow orchestrator checks them against the equipment register.
"""

import re

from app.domain.enums import ProductionImpact
from app.intelligence.config_loader import taxonomy
from app.intelligence.models import (
    EquipmentCandidate,
    ExtractedReport,
    ImpactMatch,
    SymptomMatch,
    UILanguage,
)
from app.intelligence.numbers import spoken_codes
from app.intelligence.text import Keyword, clauses, is_negated, normalize, sentence_clauses, yes_no

# "M-204", "M204", "M 204", "HX-12". Must not start inside a word ("NUMBER 204" is not "BER-204").
_DIRECT_CODE = re.compile(r"(?<![A-Z0-9])([A-Z]{1,3})\s?[-–_]?\s?(\d{2,4})(?![0-9])")
# English/Hinglish words that can precede a number but are not equipment prefixes.
_NOT_PREFIXES = {"NO", "NUM", "AT", "IN", "IS", "ON", "TO", "OF", "BY", "OR", "AN", "AM", "PM", "KA", "KI",
                 "KE", "ME", "SE", "HAI", "HE", "THE", "AND", "FOR", "BAY", "ID", "UP", "SO", "DO", "HR", "MIN",
                 "SEC", "KG", "KM", "MM", "CM", "RPM", "BAR", "PSI", "KW", "KV", "HZ"}
# "machine number 204", "मशीन नंबर 204", "నంబర్ 204": digits without a letter prefix.
_DIGITS_AFTER_WORD = re.compile(
    r"(?:number|no|num|machine|equipment|नंबर|नम्बर|मशीन|నంబర్|నెంబర్|మెషిన్)\s*(\d{2,4})(?!\d)"
)

_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2}


def _equipment_candidates(text: str) -> list[EquipmentCandidate]:
    found: list[EquipmentCandidate] = []
    seen: set[str] = set()

    def add(code: str, display: str, heard: str, method: str, confidence: str) -> None:
        if code not in seen:
            seen.add(code)
            found.append(EquipmentCandidate(code=code, display=display, heard=heard.strip(), method=method,
                                            confidence=confidence))

    upper = text.upper()
    for m in _DIRECT_CODE.finditer(upper):
        letters, digits = m.group(1), m.group(2)
        if letters in _NOT_PREFIXES:
            continue
        add(letters + digits, f"{letters}-{digits}", text[m.start():m.end()], "direct", "high")

    for letters, digits, heard in spoken_codes(text):
        add(letters + digits, f"{letters}-{digits}", heard, "spoken", "medium")

    letter_digit_codes = {c.code[len(c.code.rstrip("0123456789")):] for c in found}
    for m in _DIGITS_AFTER_WORD.finditer(normalize(text)):
        digits = m.group(1)
        if digits not in letter_digit_codes:
            add(digits, digits, m.group(0), "digits_only", "low")
    return found


def _symptoms(text: str) -> tuple[list[SymptomMatch], list[str]]:
    tax = taxonomy()
    matched: dict[str, SymptomMatch] = {}
    negated: set[str] = set()
    clause_list = clauses(text)

    for key, sym in tax.symptoms.items():
        for toks in clause_list:
            primary = _first_hit(sym.any_keywords, toks)
            if primary is None:
                continue
            if sym.with_any:
                secondary = _first_hit(sym.with_keywords, toks)
                if secondary is None:
                    continue
            else:
                secondary = None
            hits = [primary] + ([secondary] if secondary else [])
            if not sym.negation_ok and any(is_negated(toks, start, len(kw.parts)) for kw, start in hits):
                negated.add(key)
                continue
            terms = [" ".join(toks[start:start + len(kw.parts)]) for kw, start in hits]
            if key in matched:
                matched[key].terms.extend(t for t in terms if t not in matched[key].terms)
            else:
                matched[key] = SymptomMatch(key=key, category=sym.category, severity=sym.severity,
                                            safety=sym.safety, terms=terms)

    for key in list(matched):
        if any(s in matched for s in tax.symptoms[key].suppressed_by):
            del matched[key]
    return list(matched.values()), sorted(negated - set(matched))


def _first_hit(keywords: list[Keyword], toks: list[str]) -> tuple[Keyword, int] | None:
    for kw in keywords:
        starts = kw.find(toks)
        if starts:
            return kw, starts[0]
    return None


def _production_impact(text: str, focus_production: bool) -> ImpactMatch | None:
    tax = taxonomy()
    patterns = tax.production_impact.compiled()
    subjects = [Keyword.parse(s) for s in tax.production_impact.subjects]
    result: ImpactMatch | None = None
    for sentence in sentence_clauses(text):
        # A subject named earlier in the sentence carries over: "production ruk gaya tha, ab chal raha hai".
        subject_active = False
        for toks in sentence:
            clause_text = " ".join(toks)
            own_subject = any(s.find(toks) for s in subjects)
            subject_active = subject_active or own_subject
            if not subject_active and not focus_production:
                continue
            for impact in (ProductionImpact.STOPPED, ProductionImpact.DEGRADED, ProductionImpact.RUNNING):
                if any(p.search(clause_text) for p in patterns[impact]):
                    # Later clauses override earlier ones; within a clause stopped > degraded > running.
                    result = ImpactMatch(value=impact, confidence="high" if own_subject else "medium",
                                         evidence=clause_text)
                    break
    return result


def _location(text: str) -> str | None:
    m = re.search(taxonomy().location_pattern, normalize(text))
    if not m:
        return None
    return f"{m.group(1).title()} {m.group(2).upper()}"


def extract(text: str, language: UILanguage, focus: str | None = None) -> ExtractedReport:
    """Extract what the utterance explicitly states. `focus` is the field a follow-up question asked about."""
    symptoms, negated = _symptoms(text)
    safety_terms = [t for s in symptoms if s.safety for t in s.terms]
    impact = _production_impact(text, focus_production=(focus == "production_impact"))
    return ExtractedReport(
        language=language,
        text=text,
        equipment_candidates=_equipment_candidates(text),
        symptoms=symptoms,
        negated_symptoms=negated,
        production_impact=impact,
        safety_concern=bool(safety_terms),
        safety_terms=safety_terms,
        location_note=_location(text),
        answer=yes_no(text),
    )


def max_severity(severities: list[str]) -> str | None:
    return max(severities, key=_SEVERITY_RANK.__getitem__) if severities else None
