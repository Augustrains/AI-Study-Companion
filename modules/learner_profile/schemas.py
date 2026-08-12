from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProfileWorkflowReviewRequest(BaseModel):
    action: str
    corrections: dict[str, Any] = Field(default_factory=dict)


class ProfileWorkflowStartRequest(BaseModel):
    user_id: str = Field(min_length=1)
    learning_domain: str = Field(min_length=1)
    background: str = Field(min_length=1)
    self_assessed_level: str = "unknown"
    known_skill_ids: list[str] = Field(default_factory=list)
    known_skill_note: str = ""
    current_confusions: str = ""
    additional_requirements: str = ""
    preferences: dict[str, Any] = Field(default_factory=dict)
