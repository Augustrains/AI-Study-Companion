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


#用户画像字段
@dataclass
class LearnerProfile(common_api.models.UserOwned, common_api.models.Timestamped):
    learning_domain: str = ""   #机器学习、深度学习
    background: str = ""        #学习背景
    self_assessed_level: str = "unknown"    #用户自评水平
    known_knowledge_point_ids: list[str] = field(default_factory=list)
    known_knowledge_point_note: str = ""
    unknown_knowledge_point_ids: list[str] = field(default_factory=list)
    preferences: LearningPreferences = field(default_factory=LearningPreferences)   #学习偏好
    current_confusions: str = ""            #当前困惑或薄弱点
    additional_requirements: str = ""       #额外学习要求

    def to_dict(self) -> dict[str, Any]:
        return common_api.serialization.to_data(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LearnerProfile":
        return common_api.serialization.from_data(cls, payload)
