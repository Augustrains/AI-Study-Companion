"""Workflow orchestration for material question answering."""

from __future__ import annotations

from pathlib import Path

from .agent import MaterialQaAgent
from .models import MaterialQaAnswer, MaterialQaConversation
from .services import (
    MaterialQaActivityRecorder,
    MaterialQaRetriever,
    MaterialQaService,
    QdrantMaterialRetriever,
)


class MaterialQaWorkflow:
    """Coordinate conversation state, retrieval, and one Agent invocation."""

    def __init__(
        self,
        agent: MaterialQaAgent | None = None,
        retriever: MaterialQaRetriever | None = None,
        activity_recorder: MaterialQaActivityRecorder | None = None,
        qa_service: MaterialQaService | None = None,
    ) -> None:
        self.agent = agent or MaterialQaAgent()
        self.retriever = retriever or QdrantMaterialRetriever(
            documents={},
            qdrant_path=Path("data/qdrant"),
        )
        self.qa_service = qa_service or MaterialQaService(activity_recorder=activity_recorder)

    def start(self) -> None:
        """预热检索资源，不在此阶段创建或重建索引。"""

        start = getattr(self.retriever, "start", None)
        if callable(start):
            start()

    def close(self) -> None:
        close = getattr(self.retriever, "close", None)
        if callable(close):
            close()

    def create_conversation(self, *, book_id: str, user_id: str) -> MaterialQaConversation:
        return self.qa_service.create_conversation(book_id=book_id, user_id=user_id)

    def ask(
        self,
        *,
        conversation_id: str,
        book_id: str,
        question: str,
        source_ids: list[str] | None = None,
        allow_general_fallback: bool = False,
    ) -> MaterialQaAnswer:
        conversation, history = self.qa_service.begin_question(
            conversation_id=conversation_id,
            book_id=book_id,
            question=question,
        )
        retrieval = self.retriever.retrieve(
            book_id=book_id,
            question=question,
            history=history,
            source_ids=source_ids,
        )
        output = self.agent.generate(
            self.qa_service.agent_input(
                history=history,
                question=question,
                retrieval=retrieval,
                allow_general_fallback=allow_general_fallback,
            )
        )
        return self.qa_service.complete_question(conversation=conversation, output=output)
