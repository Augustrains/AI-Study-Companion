from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProfileWorkflowReviewRequest(BaseModel):
    action: str
    corrections: dict[str, Any] = Field(default_factory=dict)
