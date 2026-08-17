from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from threading import Lock, RLock
from typing import Any
from uuid import uuid4

from modules.common import api as common_api
from modules.common.errors import (
    ConflictError,
    ResourceNotFoundError,
    ValidationAppError,
)

from .models import (
    Conversation,
    ConversationMessage,
    ConversationSummary,
    ConversationTurn,
    MessageRole,
)
from .repository import SqlConversationRepository

_PROCESS_TURN_LOCKS: dict[tuple[str, str, str], RLock] = {}
_PROCESS_TURN_LOCKS_GUARD = Lock()


class ConversationService:
    """User-owned durable conversation operations; no Agent or retrieval logic."""

    def __init__(
        self,
        repository: SqlConversationRepository,
        *,
        turn_lease_seconds: int = 600,
    ) -> None:
        self.repository = repository
        if turn_lease_seconds <= 0:
            raise ValueError("turn_lease_seconds must be positive")
        self.turn_lease_seconds = int(turn_lease_seconds)
        self._database_identity = str(repository.database.engine.url)

    def _turn_lock(self, conversation_id: str, request_id: str) -> RLock:
        key = (self._database_identity, conversation_id, request_id)
        with _PROCESS_TURN_LOCKS_GUARD:
            return _PROCESS_TURN_LOCKS.setdefault(key, RLock())

    def create(
        self,
        *,
        user_id: str,
        book_id: str,
        mode: str,
        conversation_id: str | None = None,
    ) -> Conversation:
        if not user_id or not book_id or not mode:
            raise ValidationAppError("user_id, book_id and mode are required")
        now = self.repository.now()
        conversation = Conversation(
            conversation_id=conversation_id or f"conv-{uuid4().hex[:16]}",
            user_id=user_id,
            book_id=book_id,
            mode=mode,
            created_at=now,
            updated_at=now,
        )
        return self.repository.create(conversation)

    def require_owned(
        self,
        conversation_id: str,
        *,
        actor_user_id: str,
        book_id: str | None = None,
    ) -> Conversation:
        conversation = self.repository.get(conversation_id)
        if (
            conversation is None
            or conversation.user_id != actor_user_id
            or (book_id is not None and conversation.book_id != book_id)
        ):
            # Return the same 404 for missing and foreign resources to avoid ID enumeration.
            raise ResourceNotFoundError(
                "conversation not found",
                details={"conversation_id": conversation_id},
            )
        return conversation

    def append(
        self,
        conversation_id: str,
        *,
        actor_user_id: str,
        role: MessageRole,
        content: str,
        request_id: str | None = None,
        token_count: int = 0,
        book_id: str | None = None,
    ) -> ConversationMessage:
        self.require_owned(
            conversation_id,
            actor_user_id=actor_user_id,
            book_id=book_id,
        )
        content = str(content).strip()
        if not content:
            raise ValidationAppError("message content is required")
        return self.repository.append_message(
            ConversationMessage(
                message_id=f"msg-{uuid4().hex[:20]}",
                conversation_id=conversation_id,
                sequence_no=0,
                role=role,
                content=content,
                request_id=request_id,
                token_count=max(0, int(token_count)),
                created_at=self.repository.now(),
            )
        )

    def append_turn_messages(
        self,
        conversation_id: str,
        *,
        actor_user_id: str,
        book_id: str,
        request_id: str,
        question: str,
        answer: str,
        user_token_count: int = 0,
        assistant_token_count: int = 0,
    ) -> tuple[ConversationMessage, ConversationMessage]:
        """Persist one QA message pair without allowing cross-turn interleave."""

        request_id = str(request_id).strip()
        question = str(question).strip()
        answer = str(answer).strip()
        if not request_id or not question or not answer:
            raise ValidationAppError(
                "request_id, question and answer are required"
            )
        with self._turn_lock(conversation_id, request_id):
            self.require_owned(
                conversation_id,
                actor_user_id=actor_user_id,
                book_id=book_id,
            )
            user_created_at = self.repository.now()
            assistant_created_at = self.repository.now()
            return self.repository.append_turn_messages(
                ConversationMessage(
                    message_id=f"msg-{uuid4().hex[:20]}",
                    conversation_id=conversation_id,
                    sequence_no=0,
                    role="user",
                    content=question,
                    request_id=request_id,
                    token_count=max(0, int(user_token_count)),
                    created_at=user_created_at,
                ),
                ConversationMessage(
                    message_id=f"msg-{uuid4().hex[:20]}",
                    conversation_id=conversation_id,
                    sequence_no=0,
                    role="assistant",
                    content=answer,
                    request_id=request_id,
                    token_count=max(0, int(assistant_token_count)),
                    created_at=assistant_created_at,
                ),
                actor_user_id=actor_user_id,
                book_id=book_id,
            )

    def begin_turn(
        self,
        conversation_id: str,
        *,
        actor_user_id: str,
        book_id: str,
        request_id: str,
        question: str,
    ) -> ConversationTurn:
        request_id = str(request_id).strip()
        question = str(question).strip()
        if not request_id or not question:
            raise ValidationAppError("request_id and question are required")
        with self._turn_lock(conversation_id, request_id):
            conversation = self.require_owned(
                conversation_id,
                actor_user_id=actor_user_id,
                book_id=book_id,
            )
            now = self.repository.now()
            return self.repository.begin_turn(
                ConversationTurn(
                    conversation_id=conversation.conversation_id,
                    request_id=request_id,
                    user_id=conversation.user_id,
                    book_id=conversation.book_id,
                    question=question,
                    created_at=now,
                    updated_at=now,
                )
            )

    def turn(
        self,
        conversation_id: str,
        *,
        actor_user_id: str,
        book_id: str,
        request_id: str,
    ) -> ConversationTurn:
        self.require_owned(
            conversation_id,
            actor_user_id=actor_user_id,
            book_id=book_id,
        )
        turn = self.repository.get_turn(conversation_id, request_id)
        if (
            turn is None
            or turn.user_id != actor_user_id
            or turn.book_id != book_id
        ):
            raise ResourceNotFoundError(
                "conversation turn not found",
                details={
                    "conversation_id": conversation_id,
                    "request_id": request_id,
                },
            )
        return turn

    def complete_turn(
        self,
        conversation_id: str,
        *,
        actor_user_id: str,
        book_id: str,
        request_id: str,
        response: dict[str, Any],
        execution_token: str = "",
    ) -> ConversationTurn:
        normalized = self._response_payload(response)
        with self._turn_lock(conversation_id, request_id):
            self.require_owned(
                conversation_id,
                actor_user_id=actor_user_id,
                book_id=book_id,
            )
            return self.repository.complete_turn(
                conversation_id=conversation_id,
                request_id=request_id,
                actor_user_id=actor_user_id,
                book_id=book_id,
                response=normalized,
                updated_at=self.repository.now(),
                execution_token=execution_token,
            )

    def fail_turn(
        self,
        conversation_id: str,
        *,
        actor_user_id: str,
        book_id: str,
        request_id: str,
        response: dict[str, Any] | None = None,
        execution_token: str = "",
    ) -> ConversationTurn:
        normalized = self._response_payload(response or {})
        with self._turn_lock(conversation_id, request_id):
            self.require_owned(
                conversation_id,
                actor_user_id=actor_user_id,
                book_id=book_id,
            )
            return self.repository.fail_turn(
                conversation_id=conversation_id,
                request_id=request_id,
                actor_user_id=actor_user_id,
                book_id=book_id,
                response=normalized,
                updated_at=self.repository.now(),
                execution_token=execution_token,
            )

    def run_turn(
        self,
        conversation_id: str,
        *,
        actor_user_id: str,
        book_id: str,
        request_id: str,
        question: str,
        operation: Callable[[ConversationTurn], dict[str, Any]],
    ) -> ConversationTurn:
        """Run one idempotent QA operation under a local lock and SQL lease."""

        with self._turn_lock(conversation_id, request_id):
            turn = self.begin_turn(
                conversation_id,
                actor_user_id=actor_user_id,
                book_id=book_id,
                request_id=request_id,
                question=question,
            )
            if turn.status == "completed":
                return turn

            execution_token = f"turn-exec-{uuid4().hex}"
            now = self.repository.now()
            lease_expires_at = (
                datetime.fromisoformat(now)
                + timedelta(seconds=self.turn_lease_seconds)
            ).isoformat()
            claimed = self.repository.claim_turn(
                conversation_id=conversation_id,
                request_id=request_id,
                actor_user_id=actor_user_id,
                book_id=book_id,
                execution_token=execution_token,
                lease_expires_at=lease_expires_at,
                updated_at=now,
            )
            if claimed.status == "completed":
                return claimed
            try:
                response = self._response_payload(operation(claimed))
            except Exception as exc:
                try:
                    self.fail_turn(
                        conversation_id,
                        actor_user_id=actor_user_id,
                        book_id=book_id,
                        request_id=request_id,
                        response={"error_type": type(exc).__name__},
                        execution_token=execution_token,
                    )
                except (ConflictError, ResourceNotFoundError):
                    # Preserve the operation failure if a newer lease won or
                    # the owner deleted the conversation concurrently.
                    pass
                raise
            return self.complete_turn(
                conversation_id,
                actor_user_id=actor_user_id,
                book_id=book_id,
                request_id=request_id,
                response=response,
                execution_token=execution_token,
            )

    @staticmethod
    def _response_payload(response: dict[str, Any]) -> dict[str, Any]:
        normalized = common_api.serialization.to_data(response)
        if not isinstance(normalized, dict):
            raise ValidationAppError("conversation turn response must be a JSON object")
        return normalized

    def messages(
        self,
        conversation_id: str,
        *,
        actor_user_id: str,
        book_id: str | None = None,
        after_sequence: int = 0,
    ) -> list[ConversationMessage]:
        self.require_owned(
            conversation_id,
            actor_user_id=actor_user_id,
            book_id=book_id,
        )
        return self.repository.list_messages(
            conversation_id,
            after_sequence=after_sequence,
        )

    def summary(
        self,
        conversation_id: str,
        *,
        actor_user_id: str,
    ) -> ConversationSummary | None:
        self.require_owned(conversation_id, actor_user_id=actor_user_id)
        return self.repository.get_summary(conversation_id)

    def save_summary(
        self,
        summary: ConversationSummary,
        *,
        actor_user_id: str,
    ) -> ConversationSummary:
        self.require_owned(summary.conversation_id, actor_user_id=actor_user_id)
        return self.repository.upsert_summary(summary)
