"""MySQL-only seven-day learning-plan endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from .module import LearningPlanModule
from .schemas import CompleteWeeklyPlanItemRequest, GenerateWeeklyLearningPlanRequest, ReplanAfterDiagnosticRequest, WeeklyLearningPlanLookupResponse, WeeklyLearningPlanResponse


def build_router(module: LearningPlanModule) -> APIRouter:
    router = APIRouter(prefix="/api/learning-plans", tags=["learning-plan"])

    @router.get("/weekly", response_model=WeeklyLearningPlanLookupResponse)
    def get_weekly_learning_plan(user_id: int = Query(..., alias="userId", gt=0), book_id: int = Query(..., alias="bookId", gt=0)) -> dict[str, Any]:
        plan = module.get_weekly(user_id=user_id, book_id=book_id)
        return {"exists": plan is not None, "plan": plan}

    @router.post("/weekly/generate", response_model=WeeklyLearningPlanResponse)
    def generate_weekly_learning_plan(payload: GenerateWeeklyLearningPlanRequest) -> dict[str, Any]:
        return module.generate_weekly(user_id=payload.user_id, book_id=payload.book_id, start_date=payload.start_date)

    @router.get("/weekly/materials")
    def get_reading_materials(book_id: int = Query(..., alias="bookId", gt=0), item_title: str = Query(..., alias="itemTitle", min_length=1, max_length=300)) -> dict[str, Any]:
        return module.get_reading_materials(book_id=book_id, item_title=item_title)

    @router.post("/weekly/items/{item_id}/complete")
    def complete_weekly_plan_item(item_id: int, payload: CompleteWeeklyPlanItemRequest) -> dict[str, Any]:
        return module.complete_item(user_id=payload.user_id, item_id=item_id)

    @router.post("/weekly/{plan_id}/replan-after-diagnostic")
    def replan_after_diagnostic(plan_id: int, payload: ReplanAfterDiagnosticRequest) -> dict[str, Any]:
        return module.replan_after_diagnostic(plan_id=plan_id, diagnostic_session_id=payload.diagnostic_session_id)

    return router
