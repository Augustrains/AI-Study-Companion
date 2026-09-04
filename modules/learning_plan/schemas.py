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


class WeeklyLearningPlanResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    plan_id: int = Field(alias="planId")
    user_id: int = Field(alias="userId")
    book: dict[str, Any]
    goal: dict[str, Any]
    fixed_minutes: dict[str, int] = Field(alias="fixedMinutes")
    knowledge_point_workloads: list[dict[str, Any]] = Field(alias="knowledgePointWorkloads")
    deferred_knowledge_point_ids: list[int] = Field(alias="deferredKnowledgePointIds")
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
