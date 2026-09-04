from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MaterialQaSource(BaseModel):
    """可追溯的资料引用，前端用于展示来源卡片。"""

    id: str
    type: str
    title: str
    location: str
    excerpt: str
    knowledge_point_ids: list[str] = Field(default_factory=list, alias="knowledgePointIds")
    chapter_id: str = Field(default="", alias="chapterId")
    section_id: str = Field(default="", alias="sectionId")
    content_unit_id: str = Field(default="", alias="contentUnitId")
    book_id: str = Field(default="", alias="bookId")


class CreateMaterialQaConversationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    book_id: str = Field(alias="bookId", min_length=1)
    user_id: str = Field(alias="userId", min_length=1)
    reset_context: bool = Field(default=False, alias="resetContext")
    """调用方必须显式给出用户 ID。

    这里原先默认 "user_001"：前端漏传时后端静默按演示用户处理，
    结果是诊断写进一个账号、今日学习读另一个账号，闭环表面正常实则断开。
    改成必填后，漏传会立刻在联调阶段以 422 暴露出来。
    """


class CreateMaterialQaConversationResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    conversation_id: str = Field(alias="conversationId")
    book_id: str = Field(alias="bookId")
    user_id: str = Field(alias="userId")
    created_at: str = Field(alias="createdAt")
    status: str
    answer_mode: Literal["direct", "socratic"] = Field(default="direct", alias="answerMode")
    learning_task_id: str | None = Field(default=None, alias="learningTaskId")
    socratic_state: str | None = Field(default=None, alias="socraticState")


class AskMaterialQuestionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    book_id: str = Field(alias="bookId", min_length=1)
    question: str = Field(min_length=1, max_length=2000)
    user_id: str = Field(alias="userId", min_length=1)
    conversation_id: str | None = Field(default=None, alias="conversationId")
    source_ids: list[str] = Field(default_factory=list, alias="sourceIds")
    # 教材检索不足以支撑回答时，是否允许降级到通用模型。
    # 默认 false：资料问答的价值在于「答案有出处」，宁可拒答也不编造。
    # 前端只在用户看到拒答后显式点击「用通用模型回答」时才置为 true。
    allow_general_fallback: bool = Field(default=False, alias="allowGeneralFallback")
    answer_mode: Literal["direct", "socratic"] = Field(default="direct", alias="answerMode")
    learning_task_id: str | None = Field(default=None, alias="learningTaskId", max_length=64)


class FinishMaterialQaLearningTaskRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    book_id: str = Field(alias="bookId", min_length=1)
    user_id: str = Field(alias="userId", min_length=1)


class AskMaterialQuestionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    answer: str
    refused: bool
    citations: list[MaterialQaSource]
    related_knowledge_points: list[str] = Field(default_factory=list, alias="relatedKnowledgePoints")
    recommended_action: str | None = Field(default=None, alias="recommendedAction")
    conversation_id: str = Field(alias="conversationId")
    request_id: str = Field(alias="requestId")
    # 本次回答由通用模型给出、未经教材核对；此时 citations 必为空。
    answered_by_general_model: bool = Field(default=False, alias="answeredByGeneralModel")
    answer_mode: Literal["direct", "socratic"] = Field(default="direct", alias="answerMode")
    learning_task_id: str | None = Field(default=None, alias="learningTaskId")
    socratic_state: str | None = Field(default=None, alias="socraticState")
    response_quality: str | None = Field(default=None, alias="responseQuality")
    socratic_completed: bool = Field(default=False, alias="socraticCompleted")
