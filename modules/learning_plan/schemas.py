"""学习计划接口的请求和响应数据模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import LEARNING_TASK_STATUSES, LEARNING_TASK_TYPES

LearningTaskStatus = Literal[tuple(LEARNING_TASK_STATUSES)]
LearningTaskType = Literal[tuple(LEARNING_TASK_TYPES)]


class GenerateLearningPlanRequest(BaseModel):
    """从已校准诊断生成学习计划所需的请求字段。"""

    model_config = ConfigDict(populate_by_name=True)

    diagnostic_id: str = Field(alias="diagnosticId", min_length=1)
    book_id: str = Field(alias="bookId", min_length=1)
    goal: str = Field(min_length=1, max_length=200)
    # 计划实际归属以诊断记录里的 user_id 为准，这里的 userId 只用于校验
    # 「请求方就是做这次诊断的人」，防止拿别人的 diagnosticId 生成计划。
    user_id: str = Field(alias="userId", min_length=1)


class MaterialLearningPlanRequest(BaseModel):
    """从资料问答结果创建学习计划所需的字段。"""

    model_config = ConfigDict(populate_by_name=True)

    book_id: str = Field(alias="bookId", min_length=1)
    title: str = Field(min_length=1, max_length=100)
    goal: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=500)
    minutes: int = Field(default=20, ge=5, le=240)
    expected_completion_date: str = Field(default="", alias="expectedCompletionDate")
    resources: list["LearningPlanSourceResponse"] = Field(default_factory=list)
    user_id: str = Field(alias="userId", min_length=1)


class LearningPlanBookResponse(BaseModel):
    """学习计划中教材的展示信息。"""
    id: str
    title: str
    shortTitle: str


class LearningPlanSourceResponse(BaseModel):
    """学习资料的标识、位置和摘要信息。"""
    id: str
    type: str
    title: str
    location: str
    excerpt: str
    book_id: str = Field(default="", alias="bookId")
    chapter_id: str = Field(default="", alias="chapterId")
    section_id: str = Field(default="", alias="sectionId")
    content_unit_id: str = Field(default="", alias="contentUnitId")
    knowledge_point_ids: list[str] = Field(default_factory=list, alias="knowledgePointIds")

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class LearningPlanTaskResponse(BaseModel):
    """单个学习任务及其执行状态。"""
    id: str
    title: str
    type: str
    minutes: int
    status: LearningTaskStatus
    reason: str
    description: str
    learning_goal: str = Field(default="", alias="learningGoal")
    expected_completion_date: str = Field(default="", alias="expectedCompletionDate")
    knowledge_point_ids: list[str] = Field(default_factory=list, alias="knowledgePointIds")
    ability_id: str = Field(default="", alias="abilityId")
    chapter_ids: list[str] = Field(default_factory=list, alias="chapterIds")
    question_ids: list[str] = Field(default_factory=list, alias="questionIds")

    model_config = ConfigDict(populate_by_name=True)


class GenerateLearningPlanResponse(BaseModel):
    """生成学习计划接口返回的完整结构。"""
    book: LearningPlanBookResponse
    goal: str
    goalLevel: str
    tasks: list[LearningPlanTaskResponse]
    advice: list[str]
    resources: list[LearningPlanSourceResponse]


class LearningPlanLookupResponse(BaseModel):
    """查询已持久化学习计划的响应。"""

    exists: bool
    plan: GenerateLearningPlanResponse | None = None
