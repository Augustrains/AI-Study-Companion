from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from modules.common.errors import ResourceNotFoundError, ValidationAppError

from .agent import MaterialQaAgent
from .models import MaterialQaAgentInput, MaterialQaAnswer, MaterialQaConversation, MaterialQaMessage
from .retriever import MaterialQaRetriever, QdrantMaterialRetriever


class MaterialQaActivityRecorder(Protocol):
    """资料问答对学习活动记录的最小依赖。"""

    def record_qa_started(self, *, user_id: str, book_id: str, conversation_id: str) -> object:
        ...


class MaterialQaWorkflow:
    """资料问答工作流：会话管理、资料检索和 Agent 调用编排。"""

    def __init__(
        self,
        agent: MaterialQaAgent | None = None,
        retriever: MaterialQaRetriever | None = None,
        activity_recorder: MaterialQaActivityRecorder | None = None,
    ) -> None:
        self.agent = agent or MaterialQaAgent()
        self.retriever = retriever or QdrantMaterialRetriever(
            documents={},
            qdrant_path=Path("data/qdrant"),
        )
        self.activity_recorder = activity_recorder
        self.conversation: MaterialQaConversation | None = None

    def close(self) -> None:
        """释放资料问答依赖的外部资源。"""

        close = getattr(self.retriever, "close", None)
        if callable(close):
            close()

    def create_conversation(self, *, book_id: str, user_id: str) -> MaterialQaConversation:
        """创建一个新的运行时会话。"""

        self.conversation = MaterialQaConversation(
            conversation_id=f"qa-{uuid4().hex[:12]}",
            book_id=book_id,
            user_id=user_id,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        if self.activity_recorder is not None:
            self.activity_recorder.record_qa_started(
                user_id=user_id,
                book_id=book_id,
                conversation_id=self.conversation.conversation_id,
            )
        return self.conversation

    def ask(
        self,
        *,
        conversation_id: str,
        book_id: str,
        question: str,
        source_ids: list[str] | None = None,
    ) -> MaterialQaAnswer:
        """处理一轮问答：读取历史、检索资料、调用 Agent 并保存消息。"""

        conversation = self._require_conversation(conversation_id, book_id)
        history = list(conversation.messages)
        conversation.messages.append(MaterialQaMessage(role="user", content=question))

        retrieval = self.retriever.retrieve(
            book_id=book_id,
            question=question,
            history=history,
            source_ids=source_ids,
        )
        result = self.agent.generate(
            MaterialQaAgentInput(
                history=history,
                current_question=question,
                retrieval=retrieval,
            )
        )
        conversation.messages.append(MaterialQaMessage(role="assistant", content=result.answer))
        return MaterialQaAnswer(
            conversation_id=conversation.conversation_id,
            answer=result.answer,
            citations=result.citations,
            related_knowledge_points=result.related_knowledge_points,
            recommended_action=result.recommended_action,
        )

    def _require_conversation(self, conversation_id: str, book_id: str) -> MaterialQaConversation:
        """校验会话存在且属于当前书籍。"""

        if self.conversation is None or self.conversation.conversation_id != conversation_id:
            raise ResourceNotFoundError(
                "material QA conversation not found",
                details={"conversation_id": conversation_id},
            )
        if self.conversation.book_id != book_id:
            raise ValidationAppError(
                "conversation does not belong to the requested book",
                details={"conversation_id": conversation_id, "book_id": book_id},
            )
        return self.conversation
