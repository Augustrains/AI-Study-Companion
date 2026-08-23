"""学习目标接口。

    POST /api/learner-goals            保存/覆盖某用户在某本书上的目标
    GET  /api/learner-goals?userId=&bookId=   读回目标，供「选书与目标」页回填
"""

from __future__ import annotations

from typing import Any, Protocol

from fastapi import APIRouter, Query

from .module import LearnerGoalModule
from .schemas import LearnerGoalLookupResponse, LearnerGoalResponse, SaveLearnerGoalRequest


class PlanScheduler(Protocol):
    """学习计划里被本模块用到的那一小部分能力。

    只依赖这个协议而不是直接依赖 LearningPlanModule，是为了避免
    learner_goals -> learning_plan 的硬依赖，也方便测试时传桩。
    """

    def reschedule(self, *, user_id: str, book_id: str) -> dict[str, Any] | None: ...


def build_router(module: LearnerGoalModule, scheduler: PlanScheduler | None = None) -> APIRouter:
    router = APIRouter(tags=["learner-goals"])

    @router.post("/api/learner-goals", response_model=LearnerGoalResponse)
    def save_goal(payload: SaveLearnerGoalRequest) -> LearnerGoalResponse:
        previous = module.get(user_id=payload.user_id, book_id=payload.book_id)
        goal = module.save(
            user_id=payload.user_id,
            book_id=payload.book_id,
            target_level=payload.target_level,
            weekly_hours=payload.weekly_hours,
        )
        response = LearnerGoalResponse(**goal.public_view())

        hours_changed = previous is None or previous.weekly_hours != goal.weekly_hours
        level_changed = previous is not None and previous.target_level != goal.target_level

        # 每周时长变了就立刻按新预算重排日期——这一步无损，不需要问用户。
        if scheduler is not None and hours_changed:
            try:
                plan = scheduler.reschedule(user_id=payload.user_id, book_id=payload.book_id)
            except Exception:  # noqa: BLE001 - 重排失败不该让「保存目标」这件事失败
                plan = None
            if plan is not None:
                response.rescheduled = True
                budget = plan.get("timeBudget") or {}
                response.estimated_days = budget.get("estimatedDays")

        # 目标水平变了，任务内容才需要重新生成——那会丢掉已完成状态，交给用户决定。
        response.plan_refresh_suggested = level_changed
        return response

    @router.get("/api/learner-goals", response_model=LearnerGoalLookupResponse)
    def get_goal(
        user_id: str = Query(..., alias="userId", min_length=1),
        book_id: str = Query(..., alias="bookId", min_length=1),
    ) -> LearnerGoalLookupResponse:
        """没设过目标时返回 exists=false，而不是 404。

        404 在前端被约定为「接口未实现」并触发降级，用它表达「还没设过」
        会让前端误判整个接口不存在。
        """
        goal = module.get(user_id=user_id, book_id=book_id)
        if goal is None:
            return LearnerGoalLookupResponse(exists=False, goal=None)
        return LearnerGoalLookupResponse(exists=True, goal=LearnerGoalResponse(**goal.public_view()))

    return router
