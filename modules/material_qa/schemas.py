from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MaterialQaSource(BaseModel):
    """可追溯的资料引用，前端用于展示来源卡片。"""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    type: str
    title: str
    location: str
    excerpt: str
    knowledge_point_ids: list[str] = Field(
        default_factory=list, alias="knowledgePointIds"
    )
    chapter_id: str = Field(default="", alias="chapterId")
    section_id: str = Field(default="", alias="sectionId")
    content_unit_id: str = Field(default="", alias="contentUnitId")
    book_id: str = Field(default="", alias="bookId")


class CreateMaterialQaConversationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    book_id: str = Field(alias="bookId", min_length=1)
    user_id: str | None = Field(default=None, alias="userId", min_length=1)


class CreateMaterialQaConversationResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    conversation_id: str = Field(alias="conversationId")
    book_id: str = Field(alias="bookId")
    user_id: str = Field(alias="userId")
    created_at: str = Field(alias="createdAt")
    status: str


class AskMaterialQuestionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    book_id: str = Field(alias="bookId", min_length=1)
    question: str = Field(min_length=1, max_length=2000)
    user_id: str | None = Field(default=None, alias="userId", min_length=1)
    conversation_id: str | None = Field(default=None, alias="conversationId")
    request_id: str | None = Field(
        default=None,
        alias="requestId",
        min_length=8,
        max_length=128,
    )
    source_ids: list[str] = Field(default_factory=list, alias="sourceIds")


class AskMaterialQuestionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    answer: str
    refused: bool
    citations: list[MaterialQaSource]
    related_knowledge_points: list[str] = Field(
        default_factory=list, alias="relatedKnowledgePoints"
    )
    recommended_action: str | None = Field(default=None, alias="recommendedAction")
    conversation_id: str = Field(alias="conversationId")
    request_id: str = Field(alias="requestId")


class MaterialQaHistoryMessageResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    role: Literal["user", "assistant"]
    content: str
    request_id: str | None = Field(default=None, alias="requestId")
    created_at: str = Field(alias="createdAt")
    citations: list[MaterialQaSource] = Field(default_factory=list)


class MaterialQaConversationHistoryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    conversation_id: str = Field(alias="conversationId")
    book_id: str = Field(alias="bookId")
    messages: list[MaterialQaHistoryMessageResponse]
