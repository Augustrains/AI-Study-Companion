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
    known_knowledge_point_ids: list[str] = Field(default_factory=list)
    known_knowledge_point_note: str = ""
    unknown_knowledge_point_ids: list[str] = Field(default_factory=list)
    current_confusions: str = ""
    additional_requirements: str = ""
    preferences: dict[str, Any] = Field(default_factory=dict)
