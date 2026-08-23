"""学习记录接口的请求和响应模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LearningActivityResultResponse(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    score: float | None = None
    accuracy: float | None = None
    correct_count: int | None = Field(default=None, alias="correctCount")
    total_count: int | None = Field(default=None, alias="totalCount")
    duration_seconds: int | None = Field(default=None, alias="durationSeconds")
    completion_rate: float | None = Field(default=None, alias="completionRate")
    confidence: str | None = None
    level: str | None = None
    mastery_score: float | None = Field(default=None, alias="masteryScore")
    change: float | None = None


class LearningActivityResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    user_id: str = Field(alias="userId")
    category: str
    activity_type: str = Field(alias="activityType")
    status: str
    title: str
    description: str = ""
    occurred_at: str = Field(alias="occurredAt")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")

    book_id: str | None = Field(default=None, alias="bookId")
    plan_id: str | None = Field(default=None, alias="planId")
    task_id: str | None = Field(default=None, alias="taskId")
    knowledge_point_ids: list[str] = Field(default_factory=list, alias="knowledgePointIds")

    result: LearningActivityResultResponse = Field(default_factory=LearningActivityResultResponse)
    detail: dict[str, Any] = Field(default_factory=dict)


class LearningActivityListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    records: list[LearningActivityResponse]
    total: int
    page: int
    page_size: int = Field(alias="pageSize")
    has_next: bool = Field(alias="hasNext")


class LearningEventRequest(BaseModel):
    """前端写入学习任务生命周期事件的请求。"""

    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(alias="userId", min_length=1)
    """调用方必须显式给出用户 ID。

    这里原先默认 "user_001"：前端漏传时后端静默按演示用户处理，
    结果是诊断写进一个账号、今日学习读另一个账号，闭环表面正常实则断开。
    改成必填后，漏传会立刻在联调阶段以 422 暴露出来。
    """
    task_id: str = Field(alias="taskId", min_length=1)
    task_title: str = Field(default="", alias="taskTitle")
    event_type: str = Field(alias="eventType", min_length=1)
    status: str = Field(min_length=1)
    plan_id: str = Field(default="", alias="planId")
    book_id: str = Field(default="", alias="bookId")
    knowledge_point_ids: list[str] = Field(default_factory=list, alias="knowledgePointIds")
    # 用户在完成弹窗里自己填写的实际用时（秒）。0 表示未填写。
    duration_seconds: int = Field(default=0, alias="durationSeconds", ge=0)
    # 计划预估用时（分钟），与实际用时一起保存，用于后续校准排课。
    planned_minutes: int = Field(default=0, alias="plannedMinutes", ge=0)
    detail: dict[str, Any] = Field(default_factory=dict)
    client_request_id: str = Field(default="", alias="clientRequestId")


class LearningEventResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    event_id: str = Field(alias="eventId")
    activity: LearningActivityResponse
    plan_completed: bool = Field(default=False, alias="planCompleted")
    memory_updated: bool = Field(default=False, alias="memoryUpdated")
    # 这次完成带来的新用时样本是否触发了剩余任务的重排。
    plan_rescheduled: bool = Field(default=False, alias="planRescheduled")


class LearningActivityQuery(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    category: str | None = None
    activity_type: str | None = Field(default=None, alias="activityType")
    status: str | None = None
    book_id: str | None = Field(default=None, alias="bookId")
    knowledge_point_id: str | None = Field(default=None, alias="knowledgePointId")
    start_at: str | None = Field(default=None, alias="startAt")
    end_at: str | None = Field(default=None, alias="endAt")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, alias="pageSize", ge=1, le=100)
