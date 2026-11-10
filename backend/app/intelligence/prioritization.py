"""Priority from ordered, configurable rules (config/priority_rules.yaml). First match wins."""

from app.domain.enums import ProductionImpact
from app.intelligence.config_loader import PriorityRule, priority_rules
from app.intelligence.extraction import max_severity
from app.intelligence.models import PriorityContext, PriorityDecision


def _matches(rule: PriorityRule, ctx: PriorityContext) -> bool:
    when = rule.when
    if "safety_concern" in when and ctx.safety_concern != when["safety_concern"]:
        return False
    if "production_impact" in when and ctx.production_impact.value not in when["production_impact"]:
        return False
    if "equipment_critical" in when and bool(ctx.equipment_critical) != when["equipment_critical"]:
        return False
    if "has_symptoms" in when and bool(ctx.symptom_severities) != when["has_symptoms"]:
        return False
    if "max_symptom_severity" in when and max_severity(ctx.symptom_severities) not in when["max_symptom_severity"]:
        return False
    return not ("category" in when and ctx.category.value not in when["category"])


def prioritize(ctx: PriorityContext) -> PriorityDecision:
    for rule in priority_rules().rules:
        if _matches(rule, ctx):
            return PriorityDecision(
                level=rule.level,
                rule_id=rule.id,
                explanation=rule.explanation.get("en", rule.id),
                provisional=ctx.production_impact == ProductionImpact.UNKNOWN or ctx.equipment_critical is None,
            )
    raise RuntimeError("priority_rules.yaml has no catch-all rule")  # prevented by config validation
