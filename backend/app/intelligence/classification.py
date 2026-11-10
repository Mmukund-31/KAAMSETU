"""Issue category from recognised symptoms, with the registered equipment category as tie-breaker.

Scoring: a specific symptom counts 2, a generic one 1, and the equipment's own category adds 1.5.
With no symptoms the equipment category is used; with neither, the category is 'other'.
"""

from app.domain.enums import EquipmentCategory
from app.intelligence.config_loader import taxonomy
from app.intelligence.models import Classification

SPECIFIC_WEIGHT = 2.0
GENERIC_WEIGHT = 1.0
EQUIPMENT_WEIGHT = 1.5


def classify(
    symptom_keys: list[str],
    equipment_category: EquipmentCategory | None,
    override: EquipmentCategory | None = None,
) -> Classification:
    if override is not None:
        return Classification(category=override, basis="override")

    tax = taxonomy()
    scores: dict[EquipmentCategory, float] = {}
    for key in symptom_keys:
        sym = tax.symptoms.get(key)
        if sym is None:
            continue
        scores[sym.category] = scores.get(sym.category, 0.0) + (SPECIFIC_WEIGHT if sym.specific else GENERIC_WEIGHT)

    if not scores:
        if equipment_category is not None:
            return Classification(category=equipment_category, basis="equipment")
        return Classification(category=EquipmentCategory.OTHER, basis="none")

    if equipment_category is not None:
        scores[equipment_category] = scores.get(equipment_category, 0.0) + EQUIPMENT_WEIGHT
    # Deterministic tie-break: equipment category first, then enum order.
    order = list(EquipmentCategory)
    best = max(scores, key=lambda c: (scores[c], c == equipment_category, -order.index(c)))
    return Classification(category=best, basis="symptoms", scores={c.value: s for c, s in scores.items()})
