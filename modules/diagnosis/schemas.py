from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DiagnosticStartRequest(BaseModel):
    """启动诊断时前端提交的请求字段。"""

    model_config = ConfigDict(populate_by_name=True)

    book_id: str = Field(alias="bookId", min_length=1)
    learning_goal: str = Field(default="", alias="learningGoal", max_length=200)
    user_id: str = Field(default="user_001", alias="userId", min_length=1)
    learning_plan_day_id: int | None = Field(default=None, alias="learningPlanDayId", gt=0)
    learning_plan_item_id: int | None = Field(default=None, alias="learningPlanItemId", gt=0)


class DiagnosticAnswerRequest(BaseModel):
    """提交单道题答案时的请求字段。"""

    model_config = ConfigDict(populate_by_name=True)

    question_id: str = Field(alias="questionId", min_length=1)
    answer: str = Field(default="", max_length=200)
    skipped: bool = False


class DiagnosticCalibrationRequest(BaseModel):
    """用户校准诊断结果时的请求字段。"""

    model_config = ConfigDict(populate_by_name=True)

    diagnostic_id: str = Field(alias="diagnosticId", min_length=1)
    level: Literal["lower", "same", "higher"]
    reason: str = Field(default="", max_length=500)


class DiagnosticOptionResponse(BaseModel):
    """返回给前端的题目选项。"""

    id: str
    text: str


class DiagnosticQuestionResponse(BaseModel):
    """返回给前端的题目结构。"""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    title: str
    tag: str
    options: list[DiagnosticOptionResponse]
    book_id: str = Field(default="", alias="bookId")
    chapter_id: str = Field(default="", alias="chapterId")
    section_ids: list[str] = Field(default_factory=list, alias="sectionIds")
    knowledge_point_ids: list[str] = Field(default_factory=list, alias="knowledgePointIds")
    task_mode: str = Field(default="diagnostic", alias="taskMode")


class DiagnosticStartResponse(BaseModel):
    """启动诊断接口的响应结构。"""

    model_config = ConfigDict(populate_by_name=True)

    diagnostic_id: str = Field(alias="diagnosticId")
    questions: list[DiagnosticQuestionResponse]


class DiagnosticAnswerResponse(BaseModel):
    """提交答案接口的响应结构。"""

    model_config = ConfigDict(populate_by_name=True)

    diagnostic_id: str = Field(alias="diagnosticId")
    question_id: str = Field(alias="questionId")
    saved: bool


class DiagnosticFinishResponse(BaseModel):
    """完成诊断接口的响应结构。"""

    model_config = ConfigDict(populate_by_name=True)

    level: str
    accuracy: str
    confidence: str
    evidence: str
    answer_performance: str = Field(alias="answerPerformance")
    generated_at: str = Field(alias="generatedAt")
    related_scope: str = Field(alias="relatedScope")


class DiagnosticCalibrationResponse(BaseModel):
    """校准诊断接口的响应结构。"""

    model_config = ConfigDict(populate_by_name=True)

    diagnostic_id: str = Field(alias="diagnosticId")
    saved: bool
