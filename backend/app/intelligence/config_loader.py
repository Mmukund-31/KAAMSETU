"""Loads and validates the YAML configuration in app/intelligence/config.

Invalid configuration fails loudly at load time (and in the test suite), never silently at request time.
"""

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.enums import EquipmentCategory, Priority, ProductionImpact, UserRole
from app.intelligence.models import FollowUpField, Severity
from app.intelligence.text import Keyword

CONFIG_DIR = Path(__file__).resolve().parent / "config"
LANGS = ("en", "hinglish", "hi", "te")


class SymptomDef(BaseModel):
    category: EquipmentCategory
    specific: bool = False
    severity: Severity = "medium"
    safety: bool = False
    negation_ok: bool = False
    label: dict[str, str]
    any: list[str] = Field(min_length=1)
    with_any: list[str] = []
    suppressed_by: list[str] = []

    @property
    def any_keywords(self) -> list[Keyword]:
        return [Keyword.parse(k) for k in self.any]

    @property
    def with_keywords(self) -> list[Keyword]:
        return [Keyword.parse(k) for k in self.with_any]

    def label_for(self, language: str) -> str:
        lang = "en" if language == "hinglish" else language
        return self.label.get(lang) or self.label["en"]


class ImpactPatterns(BaseModel):
    subjects: list[str]
    stopped: list[str]
    degraded: list[str]
    running: list[str]

    @field_validator("stopped", "degraded", "running")
    @classmethod
    def _compile_check(cls, patterns: list[str]) -> list[str]:
        for p in patterns:
            re.compile(p)
        return patterns

    def compiled(self) -> dict[ProductionImpact, list[re.Pattern[str]]]:
        return {
            ProductionImpact.STOPPED: [re.compile(p) for p in self.stopped],
            ProductionImpact.DEGRADED: [re.compile(p) for p in self.degraded],
            ProductionImpact.RUNNING: [re.compile(p) for p in self.running],
        }


class Taxonomy(BaseModel):
    version: int
    categories: dict[EquipmentCategory, dict[str, str]]
    symptoms: dict[str, SymptomDef]
    production_impact: ImpactPatterns
    location_pattern: str

    @model_validator(mode="after")
    def _check_references(self) -> "Taxonomy":
        for key, sym in self.symptoms.items():
            unknown = set(sym.suppressed_by) - set(self.symptoms)
            if unknown:
                raise ValueError(f"symptom {key}: suppressed_by references unknown symptoms {unknown}")
            if "en" not in sym.label:
                raise ValueError(f"symptom {key}: an English label is required")
            sym.any_keywords, sym.with_keywords  # noqa: B018 - parse every keyword now
        if set(self.categories) != set(EquipmentCategory):
            raise ValueError("taxonomy.categories must list every EquipmentCategory")
        re.compile(self.location_pattern)
        return self

    def category_label(self, category: EquipmentCategory, language: str) -> str:
        lang = "en" if language == "hinglish" else language
        labels = self.categories[category]
        return labels.get(lang) or labels["en"]


class PriorityRule(BaseModel):
    id: str
    level: Priority
    when: dict[str, Any]
    explanation: dict[str, str]

    @field_validator("when")
    @classmethod
    def _known_conditions(cls, when: dict[str, Any]) -> dict[str, Any]:
        allowed = {"safety_concern", "production_impact", "equipment_critical", "has_symptoms",
                   "max_symptom_severity", "category"}
        unknown = set(when) - allowed
        if unknown:
            raise ValueError(f"unknown priority conditions: {unknown}")
        for key in ("production_impact",):
            for v in when.get(key, []):
                ProductionImpact(v)
        for v in when.get("category", []):
            EquipmentCategory(v)
        return when


class PriorityRules(BaseModel):
    version: int
    rules: list[PriorityRule] = Field(min_length=1)

    @model_validator(mode="after")
    def _ends_with_catch_all(self) -> "PriorityRules":
        if self.rules[-1].when:
            raise ValueError("the last priority rule must have no conditions (catch-all)")
        if len({r.id for r in self.rules}) != len(self.rules):
            raise ValueError("priority rule ids must be unique")
        return self


class WorkflowPolicy(BaseModel):
    version: int
    required_fields: list[FollowUpField]
    approval_required_for_roles: list[UserRole]
    max_utterances: int = Field(ge=2, le=20)


class Responses(BaseModel):
    version: int
    priority_labels: dict[str, dict[Priority, str]]
    messages: dict[str, dict[str, str]]

    @model_validator(mode="after")
    def _every_language_present(self) -> "Responses":
        for key, by_lang in self.messages.items():
            missing = set(LANGS) - set(by_lang)
            if missing:
                raise ValueError(f"message {key} is missing languages {missing}")
        if set(self.priority_labels) != set(LANGS):
            raise ValueError("priority_labels must cover en, hinglish, hi, te")
        return self


def _load(name: str) -> dict[str, Any]:
    with (CONFIG_DIR / name).open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def taxonomy() -> Taxonomy:
    return Taxonomy.model_validate(_load("taxonomy.yaml"))


@lru_cache
def priority_rules() -> PriorityRules:
    return PriorityRules.model_validate(_load("priority_rules.yaml"))


@lru_cache
def workflow_policy() -> WorkflowPolicy:
    return WorkflowPolicy.model_validate(_load("workflow_policy.yaml"))


@lru_cache
def responses() -> Responses:
    return Responses.model_validate(_load("responses.yaml"))
