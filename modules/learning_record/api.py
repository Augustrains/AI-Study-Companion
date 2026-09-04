from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from modules.common import api as common_api

from .module import LearningRecordModule
from .schemas import LearningActivityListResponse, LearningActivityResponse, LearningEventRequest, LearningEventResponse


def build_router(module: LearningRecordModule) -> APIRouter:
    router = APIRouter(tags=["learning-records"])

    @router.post("/api/learning-events", response_model=LearningEventResponse)
    def write_learning_event(payload: LearningEventRequest) -> LearningEventResponse:
        """写入学习任务开始、完成、暂停或跳过事件。"""
        activity = module.record_learning_event(
            user_id=payload.user_id.strip(),
            task_id=payload.task_id.strip(),
            task_title=payload.task_title.strip(),
            event_type=payload.event_type,
            status=payload.status,
            plan_id=payload.plan_id,
            book_id=payload.book_id,
            knowledge_point_ids=payload.knowledge_point_ids,
            detail=payload.detail,
            client_request_id=payload.client_request_id,
        )
        return LearningEventResponse(
            eventId=activity.id,
            activity=common_activity_to_response(activity),
            planCompleted=False,
            memoryUpdated=False,
        )

    @router.get("/api/learning-records", response_model=LearningActivityListResponse)
    def list_records(
        user_id: str = Query(..., alias="userId", min_length=1),
        category: str | None = None,
        activity_type: str | None = Query(default=None, alias="activityType"),
        status: str | None = None,
        book_id: str | None = Query(default=None, alias="bookId"),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    ) -> LearningActivityListResponse:
        result = module.list_activities(
            user_id.strip(),
            category=category,
            activity_type=activity_type,
            status=status,
            book_id=book_id,
            page=page,
            page_size=page_size,
        )
        response_data = {
            **result,
            "records": [common_api.serialization.to_data(activity) for activity in result["records"]],
        }
        return LearningActivityListResponse.model_validate(response_data)

    @router.get("/api/learning-records/{activity_id}", response_model=LearningActivityResponse)
    def get_record(
        activity_id: str,
        user_id: str = Query(..., alias="userId", min_length=1),
    ) -> LearningActivityResponse:
        activity = module.get_activity(user_id.strip(), activity_id.strip())
        if activity is None:
            raise HTTPException(status_code=404, detail={"code": "RECORD_NOT_FOUND", "message": "learning activity not found"})
        return LearningActivityResponse.model_validate(common_activity_to_response(activity))

    return router


def common_activity_to_response(activity: object) -> dict[str, object]:
    """将领域对象转换为 Schema 可接受的 snake_case 数据。"""

    from modules.common import api as common_api

    return common_api.serialization.to_data(activity)
