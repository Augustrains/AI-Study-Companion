from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modules.common import api as common_api


@dataclass
class LearningPreferences:
    activity_types: list[str] = field(default_factory=lambda: ["reading", "quiz"])
    content_style: str = "balanced"
    difficulty: str = "adaptive"
    session_duration_minutes: int = 30
    learning_frequency: str = "flexible"


@dataclass
class LearnerProfile(common_api.models.UserOwned, common_api.models.Timestamped):
    learning_domain: str = ""
    background: str = ""
    self_assessed_level: str = "unknown"
    known_skill_ids: list[str] = field(default_factory=list)
    known_skill_note: str = ""
    preferences: LearningPreferences = field(default_factory=LearningPreferences)
    current_confusions: str = ""
    additional_requirements: str = ""

    def to_dict(self) -> dict[str, Any]:
        return common_api.serialization.to_data(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LearnerProfile":
        return common_api.serialization.from_data(cls, payload)
