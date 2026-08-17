from __future__ import annotations

from uuid import uuid4

from modules.common.errors import ResourceNotFoundError, ValidationAppError

from .models import Conversation, ConversationMessage, ConversationSummary, MessageRole
from .repository import SqlConversationRepository


class ConversationService:
    """User-owned durable conversation operations; no Agent or retrieval logic."""

    def __init__(self, repository: SqlConversationRepository) -> None:
        self.repository = repository

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
