"""HTTP schemas for the MySQL-backed seven-day planning API."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GenerateWeeklyLearningPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    user_id: int = Field(alias="userId", gt=0)
    book_id: int = Field(alias="bookId", gt=0)
    start_date: date | None = Field(default=None, alias="startDate")
    reason: str = Field(default="", max_length=1000)
    # The planning dialog can optionally change the target and regenerate in
    # one operation.  Keeping this on the planning request makes the new goal
    # part of the exact context used to create the replacement tasks.
    aim_level: int | None = Field(default=None, alias="aimLevel", ge=0, le=3)


class WeeklyLearningPlanResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    plan_id: int = Field(alias="planId")
    user_id: int = Field(alias="userId")
    book: dict[str, Any]
    goal: dict[str, Any]
    fixed_minutes: dict[str, int] = Field(alias="fixedMinutes")
    knowledge_point_workloads: list[dict[str, Any]] = Field(alias="knowledgePointWorkloads")
    deferred_knowledge_point_ids: list[int] = Field(alias="deferredKnowledgePointIds")
    prepared_content: dict[str, int] = Field(default_factory=dict, alias="preparedContent")
    advice: list[str] = Field(default_factory=list)
    resources: list[dict[str, Any]] = Field(default_factory=list)
    days: list[dict[str, Any]]


class WeeklyLearningPlanLookupResponse(BaseModel):
    exists: bool
    plan: dict[str, Any] | None = None


class ReplanAfterDiagnosticRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    diagnostic_session_id: int = Field(alias="diagnosticSessionId", gt=0)


class CompleteWeeklyPlanItemRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    user_id: int = Field(alias="userId", gt=0)

class ExecuteCodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=50_000)
    tests: list[str] = Field(min_length=1, max_length=20)
