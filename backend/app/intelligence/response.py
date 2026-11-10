"""Response text from configured templates (config/responses.yaml). No free-form generation."""

import string

from app.domain.enums import Priority
from app.intelligence.config_loader import responses


class _Strict(dict):
    def __missing__(self, key: str) -> str:
        raise KeyError(f"response template needs '{key}'")


def placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def render(key: str, language: str, **params: str) -> str:
    template = responses().messages[key][language]
    return template.format_map(_Strict(params))


def priority_label(priority: Priority, language: str) -> str:
    return responses().priority_labels[language][priority]
