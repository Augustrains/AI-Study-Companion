from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class LearningPreferences:
    activity_types: list[str] = field(default_factory=lambda: ["reading", "quiz"])
    content_style: str = "balanced"
    difficulty: str = "adaptive"
    session_duration_minutes: int = 30
    learning_frequency: str = "flexible"


@dataclass
class LearnerProfile:
    """Structured, cross-session learner profile.

    This model intentionally contains stable profile data only. Conversation
    memories and one-off observations belong in a separate memory store.
    """

    user_id: str
    learning_domain: str = ""
    background: str = ""
    self_assessed_level: str = "unknown"
    known_skill_ids: list[str] = field(default_factory=list)
    known_skill_note: str = ""
    preferences: LearningPreferences = field(default_factory=LearningPreferences)
    current_confusions: str = ""
    additional_requirements: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LearnerProfile":
        data = dict(payload)
        preferences = data.get("preferences") or {}
        data["preferences"] = LearningPreferences(**preferences)
        return cls(**data)

