"""Workflow orchestration for material question answering."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from threading import Lock, RLock
from uuid import uuid4

from modules.common.errors import ConflictError, ValidationAppError
from modules.context.builder import ContextBuilder
from modules.context.models import ContextEnvelope

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
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self.agent = agent or MaterialQaAgent()
        self.retriever = retriever or QdrantMaterialRetriever(
            documents={},
            qdrant_path=Path("data/qdrant"),
        )
        self.qa_service = qa_service or MaterialQaService(
            activity_recorder=activity_recorder
        )
        self.context_builder = context_builder
        self._turn_locks: dict[tuple[str, str], RLock] = {}
        self._turn_locks_guard = Lock()
        self._in_memory_turns: dict[
            tuple[str, str], tuple[str, MaterialQaAnswer]
        ] = {}

    def _turn_lock(self, conversation_id: str, request_id: str) -> RLock:
        with self._turn_locks_guard:
            return self._turn_locks.setdefault(
                (conversation_id, request_id),
                RLock(),
            )

    def start(self) -> None:
        """预热检索资源，不在此阶段创建或重建索引。"""

        start = getattr(self.retriever, "start", None)
        if callable(start):
            start()

    def close(self) -> None:
        close = getattr(self.retriever, "close", None)
        if callable(close):
            close()

    def create_conversation(
        self, *, book_id: str, user_id: str
    ) -> MaterialQaConversation:
        return self.qa_service.create_conversation(book_id=book_id, user_id=user_id)

    def ask(
        self,
        *,
        conversation_id: str,
        book_id: str,
        question: str,
        source_ids: list[str] | None = None,
        actor_user_id: str | None = None,
        request_id: str | None = None,
    ) -> MaterialQaAnswer:
        existing = self.qa_service.require_conversation(
            conversation_id,
            book_id,
            actor_user_id=actor_user_id,
        )
        actor = actor_user_id or existing.user_id
        request_id = request_id or f"qa-request-{uuid4().hex[:16]}"
        if self.qa_service.conversations is not None:
            if not actor_user_id:
                raise ValidationAppError("actor_user_id is required")
            turn = self.qa_service.conversations.run_turn(
                conversation_id,
                actor_user_id=actor,
                book_id=book_id,
                request_id=request_id,
                question=question,
                operation=lambda _turn: self.qa_service.answer_payload(
                    self._generate_answer(
                        conversation_id=conversation_id,
                        book_id=book_id,
                        question=question,
                        source_ids=source_ids,
                        actor_user_id=actor,
                        request_id=request_id,
                    )
                ),
            )
            answer = self.qa_service.answer_from_payload(
                conversation_id=conversation_id,
                request_id=request_id,
                payload=turn.response,
            )
            # The answer is durable before the pair is appended.  If message
            # persistence fails, retry reuses the completed turn and repairs
            # the same idempotent user/assistant pair without another LLM call.
            self.qa_service.commit_turn_messages(
                conversation_id=conversation_id,
                book_id=book_id,
                actor_user_id=actor,
                request_id=request_id,
                question=question,
                answer=answer.answer,
            )
            return answer

        key = (conversation_id, request_id)
        with self._turn_lock(*key):
            previous = self._in_memory_turns.get(key)
            if previous is not None:
                previous_question, previous_answer = previous
                if previous_question != question:
                    raise ConflictError(
                        "material QA request id has a different question",
                        details={"request_id": request_id},
                    )
                return previous_answer
            answer = self._generate_answer(
                conversation_id=conversation_id,
                book_id=book_id,
                question=question,
                source_ids=source_ids,
                actor_user_id=actor_user_id,
                request_id=request_id,
            )
            self.qa_service.commit_turn_messages(
                conversation_id=conversation_id,
                book_id=book_id,
                actor_user_id=actor,
                request_id=request_id,
                question=question,
                answer=answer.answer,
            )
            self._in_memory_turns[key] = (question, answer)
            return answer

    def _generate_answer(
        self,
        *,
        conversation_id: str,
        book_id: str,
        question: str,
        source_ids: list[str] | None,
        actor_user_id: str | None,
        request_id: str,
    ) -> MaterialQaAnswer:
        existing = self.qa_service.require_conversation(
            conversation_id,
            book_id,
            actor_user_id=actor_user_id,
        )
        retrieval_history = list(existing.messages)
        if self.context_builder is not None:
            if not actor_user_id:
                raise ValidationAppError("actor_user_id is required")
            retrieval_context = self.context_builder.for_tutor(
                request_id=f"{request_id}:retrieval",
                user_id=actor_user_id,
                book_id=book_id,
                conversation_id=conversation_id,
                current_input=question,
            )
            retrieval_history = self._history_from_context(retrieval_context)
        # Retrieval stays an independent service.  It receives the same
        # bounded conversation history as before and returns ranked chunks;
        # only the downstream prompt-composition boundary applies the final
        # learner-context and prompt budget.
        retrieval = self.retriever.retrieve(
            book_id=book_id,
            question=question,
            history=retrieval_history,
            source_ids=source_ids,
        )
        context = None
        if self.context_builder is not None:
            relevant_point_ids = sorted(
                {
                    point_id
                    for chunk in retrieval.chunks
                    for point_id in chunk.source.knowledge_point_ids
                    if point_id
                }
            )
            context = self.context_builder.for_tutor(
                request_id=request_id,
                user_id=actor_user_id,
                book_id=book_id,
                conversation_id=conversation_id,
                current_input=question,
                knowledge_point_ids=relevant_point_ids,
            )
        history = list(existing.messages)
        if context is not None:
            history = self._history_from_context(context)
        agent_input = self.qa_service.agent_input(
            history=history,
            question=question,
            retrieval=retrieval,
        )
        if context is not None:
            agent_input = replace(agent_input, context=context)
        try:
            output = self.agent.generate(agent_input)
        finally:
            if context is not None:
                self.context_builder.record_trace(context)
        return self.qa_service.answer_from_output(
            conversation_id=conversation_id,
            output=output,
            request_id=request_id,
        )

    @staticmethod
    def _history_from_context(context: ContextEnvelope):
        from .models import MaterialQaMessage

        history = []
        if context.conversation.summary:
            history.append(
                MaterialQaMessage(
                    role="assistant",
                    content=(
                        "此前会话的结构化摘要（不作为掌握度证据）："
                        + json.dumps(context.conversation.summary, ensure_ascii=False)
                    ),
                )
            )
        history.extend(
            MaterialQaMessage(
                role=message.role,
                content=message.content,
                created_at=message.created_at,
            )
            for message in context.conversation.recent_messages
            if message.role in {"user", "assistant"}
        )
        return history
