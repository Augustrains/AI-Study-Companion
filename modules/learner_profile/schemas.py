from __future__ import annotations

from pydantic import BaseModel, Field


class ProfileSetupRequest(BaseModel):
    """The only user-entered fields persisted by the MySQL profile setup."""

    user_id: int = Field(gt=0)
    book_id: int = Field(gt=0)
    background: str = Field(min_length=1, max_length=10_000)
    preferred_content_style: str = Field(min_length=1, max_length=256)
    goal: str = Field(min_length=1, max_length=256)
    aim_level: int = Field(ge=0, le=3)
    daily_minutes: int = Field(gt=0, le=1_440)
    start_date: str | None = None
    target_date: str | None = None
