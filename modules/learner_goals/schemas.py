"""学习目标接口的请求/响应模型。"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class SaveLearnerGoalRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    book_id: str = Field(alias="bookId", min_length=1)
    target_level: str = Field(alias="targetLevel", min_length=1, max_length=60)
    daily_minutes: int = Field(alias="dailyMinutes", ge=1, le=1440)
    target_date: date | None = Field(default=None, alias="targetDate")
    user_id: str = Field(alias="userId", min_length=1)


class LearnerGoalResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    goal_id: str = Field(alias="goalId")
    user_id: str = Field(alias="userId")
    book_id: str = Field(alias="bookId")
    target_level: str = Field(alias="targetLevel")
    daily_minutes: int = Field(alias="dailyMinutes")
    target_date: str | None = Field(default=None, alias="targetDate")
    updated_at: str = Field(alias="updatedAt")
    # 保存目标后是否顺带重排了在途计划的任务日期（只改日期，无损）。
    rescheduled: bool = False
    # 重排后预计多少天完成；没有在途计划时为 null。
    estimated_days: int | None = Field(default=None, alias="estimatedDays")
    # 目标水平变了：任务内容本身该跟着变，但重新生成会丢掉当前进度，
    # 所以只提示、不自动做，由用户决定要不要重做一次诊断。
    plan_refresh_suggested: bool = Field(default=False, alias="planRefreshSuggested")


class LearnerGoalLookupResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    exists: bool
    goal: LearnerGoalResponse | None = None
