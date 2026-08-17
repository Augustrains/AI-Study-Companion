from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from modules.context.models import ContextEnvelope

from .schemas import MaterialQaSource

MessageRole = Literal["user", "assistant"]


@dataclass
class MaterialQaMessage:
    """资料问答会话中的一条消息。"""

    role: MessageRole
    content: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class MaterialQaConversation:
    """一次运行时资料问答会话及其消息。"""

    conversation_id: str
    book_id: str
    user_id: str
    created_at: str
    messages: list[MaterialQaMessage] = field(default_factory=list)


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
    context: ContextEnvelope | None = None


@dataclass(frozen=True)
class MaterialQaAgentOutput:
    """Agent 生成的一次问答结果。"""

    answer: str
    refused: bool
    citations: list[MaterialQaSource]
    related_knowledge_points: list[str]
    recommended_action: str


@dataclass(frozen=True)
class MaterialQaAnswer:
    """Workflow 返回给 API 层的资料问答结果。"""

    conversation_id: str
    answer: str
    refused: bool
    citations: list[MaterialQaSource]
    related_knowledge_points: list[str]
    recommended_action: str
    request_id: str = ""
