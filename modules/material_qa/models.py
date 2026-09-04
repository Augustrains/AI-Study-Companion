from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from .schemas import MaterialQaSource

MessageRole = Literal["user", "assistant"]
AnswerMode = Literal["direct", "socratic"]
SocraticStateName = Literal["probe", "clarify", "confront", "scaffold", "confirm"]
ResponseQuality = Literal["correct", "partial", "wrong", "confused", "no_response"]


@dataclass
class MaterialQaMessage:
    """资料问答会话中的一条消息。"""

    role: MessageRole
    content: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    answer_mode: AnswerMode = "direct"
    learning_task_id: str | None = None
    socratic_state: SocraticStateName | None = None
    response_quality: ResponseQuality | None = None
    socratic_completed: bool = False


@dataclass(frozen=True)
class MaterialQaLearningTask:
    """Persisted state for one explicitly started Socratic learning task."""

    learning_task_id: str
    root_question: str
    state: SocraticStateName
    turns_in_state: int = 0
    completed: bool = False
    last_assistant_message: str = ""


@dataclass
class MaterialQaConversation:
    """一次运行时资料问答会话及其消息。"""

    conversation_id: str
    book_id: str
    user_id: str
    created_at: str
    messages: list[MaterialQaMessage] = field(default_factory=list)
    active_learning_task: MaterialQaLearningTask | None = None


@dataclass(frozen=True)
class MaterialQaRetrievedChunk:
    """RAG 检索返回的一段文本及其来源信息。"""

    text: str
    source: MaterialQaSource
    score: float


@dataclass(frozen=True)
class MaterialQaRetrievalResult:
    """一次检索的完整结果，供 Workflow 和 Agent 使用。"""

    chunks: list[MaterialQaRetrievedChunk]

    @property
    def text(self) -> str:
        """将检索片段拼接为传给 Agent 的上下文文本。"""
        return "\n\n".join(chunk.text for chunk in self.chunks)

    @property
    def citations(self) -> list[MaterialQaSource]:
        """返回检索片段对应的资料引用。"""
        return [chunk.source for chunk in self.chunks]


@dataclass(frozen=True)
class MaterialQaAgentInput:
    """Workflow 传给 Agent 的一次问答输入。"""

    history: list[MaterialQaMessage]
    current_question: str
    retrieval: MaterialQaRetrievalResult
    # 检索不足时是否允许改用通用模型作答（由 API 层透传，默认关闭）。
    allow_general_fallback: bool = False
    answer_mode: AnswerMode = "direct"
    learning_task_id: str | None = None
    socratic_state: SocraticStateName | None = None
    socratic_directive: str = ""
    root_question: str = ""


@dataclass(frozen=True)
class MaterialQaAgentOutput:
    """Agent 生成的一次问答结果。"""

    answer: str
    refused: bool
    citations: list[MaterialQaSource]
    related_knowledge_points: list[str]
    recommended_action: str
    # True 表示这条回答来自通用模型、没有教材出处，前端需要单独标注。
    answered_by_general_model: bool = False
    answer_mode: AnswerMode = "direct"
    learning_task_id: str | None = None
    socratic_state: SocraticStateName | None = None
    response_quality: ResponseQuality | None = None
    socratic_completed: bool = False


@dataclass(frozen=True)
class MaterialQaAnswer:
    """Workflow 返回给 API 层的资料问答结果。"""

    conversation_id: str
    answer: str
    refused: bool
    citations: list[MaterialQaSource]
    related_knowledge_points: list[str]
    recommended_action: str
    answered_by_general_model: bool = False
    answer_mode: AnswerMode = "direct"
    learning_task_id: str | None = None
    socratic_state: SocraticStateName | None = None
    response_quality: ResponseQuality | None = None
    socratic_completed: bool = False
