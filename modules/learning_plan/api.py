"""MySQL-only seven-day learning-plan endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from .module import LearningPlanModule
from .schemas import CompleteWeeklyPlanItemRequest, ExecuteCodeRequest, GenerateWeeklyLearningPlanRequest, ReplanAfterDiagnosticRequest, WeeklyLearningPlanLookupResponse, WeeklyLearningPlanResponse


def build_router(module: LearningPlanModule) -> APIRouter:
    router = APIRouter(prefix="/api/learning-plans", tags=["learning-plan"])

    @router.get("/weekly", response_model=WeeklyLearningPlanLookupResponse)
    def get_weekly_learning_plan(user_id: int = Query(..., alias="userId", gt=0), book_id: int = Query(..., alias="bookId", gt=0)) -> dict[str, Any]:
        plan = module.get_weekly(user_id=user_id, book_id=book_id)
        return {"exists": plan is not None, "plan": plan}

    @router.post("/weekly/generate", response_model=WeeklyLearningPlanResponse)
    def generate_weekly_learning_plan(payload: GenerateWeeklyLearningPlanRequest) -> dict[str, Any]:
        return module.generate_weekly(
            user_id=payload.user_id,
            book_id=payload.book_id,
            start_date=payload.start_date,
            reason=payload.reason,
            aim_level=payload.aim_level,
        )

    @router.get("/weekly/materials")
    def get_reading_materials(book_id: int = Query(..., alias="bookId", gt=0), item_title: str = Query(..., alias="itemTitle", min_length=1, max_length=300)) -> dict[str, Any]:
        return module.get_reading_materials(book_id=book_id, item_title=item_title)

    @router.post("/weekly/items/{item_id}/complete")
    def complete_weekly_plan_item(item_id: int, payload: CompleteWeeklyPlanItemRequest) -> dict[str, Any]:
        return module.complete_item(user_id=payload.user_id, item_id=item_id)

    @router.post("/weekly/items/{item_id}/start")
    def start_weekly_plan_item(item_id: int, payload: CompleteWeeklyPlanItemRequest) -> dict[str, Any]:
        return module.start_item(user_id=payload.user_id, item_id=item_id)

    @router.post("/code/execute")
    def execute_code(payload: ExecuteCodeRequest) -> dict[str, Any]:
        return module.execute_code(code=payload.code, tests=payload.tests)

    @router.get("/weekly/items/{item_id}/content")
    def get_item_content(item_id: int) -> dict[str, Any]:
        content = module.repository.load_prepared_content(item_id=item_id)
        if not content:
            return {"kind": "unavailable", "message": "任务内容仍在准备中，请稍后重试。"}
        # 兼容旧计划：旧版本只写入了 assert True 占位测试，首次打开时原地升级，
        # 这样无需用户丢弃整份计划，数据库也会得到真实测试和参考答案。
        if content.get("kind") == "coding" and (int(content.get("format_version", 0)) < 4 or "top_k(values" in str(content.get("starter_code", ""))):
            import re, json
            title = str(module.repository.load_plan_item_title(item_id=item_id) or "")
            match = re.search(r"编程实践：(.+?)(?:（|$)", title)
            if match:
                upgraded = {"format_version": 4, "kind": "coding", "language": "python", **module._coding_challenge(match.group(1).strip())}
                module.repository.save_prepared_content(item_id=item_id, status="ready", payload=json.dumps(upgraded, ensure_ascii=False))
                content = upgraded
        # 参考答案和评分说明只保存在数据库供服务端审计，绝不下发到浏览器。
        if content.get("kind") == "coding":
            has_reference_answer = bool(content.get("solution_code"))
            content = {key: value for key, value in content.items() if key not in {"solution_code", "evaluation_notes"}}
            content["reference_answer_available"] = has_reference_answer
        return content

    @router.post("/weekly/{plan_id}/replan-after-diagnostic")
    def replan_after_diagnostic(plan_id: int, payload: ReplanAfterDiagnosticRequest) -> dict[str, Any]:
        return module.replan_after_diagnostic(plan_id=plan_id, diagnostic_session_id=payload.diagnostic_session_id)

    return router
