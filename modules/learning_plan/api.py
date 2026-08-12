"""学习计划模块的 HTTP 路由定义。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from .module import LearningPlanModule
from .schemas import GenerateLearningPlanRequest, GenerateLearningPlanResponse, LearningPlanLookupResponse, MaterialLearningPlanRequest


def build_router(module: LearningPlanModule) -> APIRouter:
    """创建学习计划相关的 FastAPI 路由。"""
    router = APIRouter(tags=["learning-plan"])

    @router.get("/api/learning-plans", response_model=LearningPlanLookupResponse)
    def get_learning_plan(
        book_id: str = Query(..., alias="bookId", min_length=1),
        diagnostic_id: str | None = Query(default=None, alias="diagnosticId"),
    ) -> dict[str, Any]:
        plan = module.get_saved(book_id=book_id, diagnostic_id=diagnostic_id)
        return {"exists": plan is not None, "plan": plan}

    @router.post("/api/learning-plans/generate", response_model=GenerateLearningPlanResponse)
    def generate_learning_plan(payload: GenerateLearningPlanRequest) -> dict[str, Any]:
        """根据诊断编号、教材和学习目标生成学习计划。"""
        return module.generate(
            diagnostic_id=payload.diagnostic_id,
            book_id=payload.book_id,
            goal=payload.goal,
        )

    @router.post("/api/learning-plans/material", response_model=GenerateLearningPlanResponse)
    def create_material_learning_plan(payload: MaterialLearningPlanRequest) -> dict[str, Any]:
        """根据资料问答来源创建一个可执行的学习计划任务。"""
        return module.create_from_material(
            book_id=payload.book_id,
            title=payload.title,
            goal=payload.goal,
            description=payload.description,
            minutes=payload.minutes,
            expected_completion_date=payload.expected_completion_date,
            resources=[resource.model_dump() for resource in payload.resources],
        )

    return router
