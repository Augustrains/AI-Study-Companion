"""Shared profile form validation rules used by contract tests and adapters."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SESSION_DURATION_CHOICES = {15, 30, 45, 60, 90, 120}

@dataclass(frozen=True)
class Rule:
    choices: tuple[str, ...] = ()

PROFILE_SCHEMA = {"self_assessed_level": Rule(("none", "basic", "practice", "independent"))}
PREFERENCE_SCHEMA = {
    "content_style": Rule(("balanced", "concise", "detailed", "example_first")),
    "difficulty": Rule(("adaptive", "easy", "challenging")),
    "learning_frequency": Rule(("daily", "frequent", "occasional", "flexible")),
}

def parse_profile_payload(payload: dict[str, Any]) -> dict[str, Any]:
    prefs = dict(payload.get("preferences") or {})
    level = str(payload.get("self_assessed_level", "none"))
    if level not in PROFILE_SCHEMA["self_assessed_level"].choices:
        raise ValueError("invalid self_assessed_level")
    for key, rule in PREFERENCE_SCHEMA.items():
        if str(prefs.get(key)) not in rule.choices:
            raise ValueError(f"invalid preference: {key}")
    minutes = int(prefs.get("session_duration_minutes", 0))
    if minutes not in SESSION_DURATION_CHOICES:
        raise ValueError("invalid session_duration_minutes")
    return {**payload, "preferences": prefs}

def normalize_profile(payload: dict[str, Any], catalog: list[str]) -> Any:
    """Keep only explicitly selected knowledge points that exist in the catalog."""
    from types import SimpleNamespace
    known = [str(x) for x in payload.get("known_knowledge_point_ids", []) if str(x) in catalog]
    unknown = [str(x) for x in payload.get("unknown_knowledge_point_ids", []) if str(x) in catalog]
    return SimpleNamespace(known_knowledge_point_ids=known, unknown_knowledge_point_ids=unknown)
