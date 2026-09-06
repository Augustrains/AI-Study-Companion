from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProfileSetupRequest(BaseModel):
    """The only user-entered fields persisted by the MySQL profile setup."""

    user_id: int = Field(gt=0)
    book_id: int = Field(gt=0)
    background: str = Field(min_length=1, max_length=10_000)
    preferred_content_style: str = Field(min_length=1, max_length=256)
    preferred_difficulty: Literal["adaptive", "easy", "challenging"] = "adaptive"
    learning_frequency: Literal["daily", "frequent", "occasional", "flexible"] = "flexible"
    self_assessed_level: str = Field(default="unknown", min_length=1, max_length=32)
    current_confusions: str = Field(default="", max_length=10_000)
    additional_requirements: str = Field(default="", max_length=10_000)
    preferred_activity_types: list[str] = Field(default_factory=list, max_length=16)
    session_duration_minutes: int | None = Field(default=None, ge=1, le=1_440)
    goal: str = Field(min_length=1, max_length=256)
    aim_level: int = Field(ge=0, le=3)
    daily_minutes: int = Field(gt=0, le=1_440)
    start_date: str | None = None
    target_date: str | None = None
