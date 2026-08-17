from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from modules.common.errors import ConflictError, ResourceNotFoundError
from modules.persistence.database import Database
from modules.persistence.tables import (
    ConversationMessageRow,
    ConversationRow,
    ConversationSummaryRow,
)

from .models import Conversation, ConversationMessage, ConversationSummary


class SqlConversationRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _conversation(row: ConversationRow) -> Conversation:
        return Conversation(
            conversation_id=row.conversation_id,
            user_id=row.user_id,
            book_id=row.book_id,
            mode=row.mode,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
            version=row.version,
        )

    @staticmethod
    def _message(row: ConversationMessageRow) -> ConversationMessage:
        return ConversationMessage(
            message_id=row.message_id,
            conversation_id=row.conversation_id,
            sequence_no=row.sequence_no,
            role=row.role,
            content=row.content,
            request_id=row.request_id,
            token_count=row.token_count,
            created_at=row.created_at,
        )

    def create(self, conversation: Conversation) -> Conversation:
        with self.database.session() as session:
            if session.get(ConversationRow, conversation.conversation_id) is not None:
                raise ConflictError(
                    "conversation already exists",
                    details={"conversation_id": conversation.conversation_id},
                )
            session.add(
                ConversationRow(
                    conversation_id=conversation.conversation_id,
                    user_id=conversation.user_id,
                    book_id=conversation.book_id,
                    mode=conversation.mode,
                    status=conversation.status,
                    created_at=conversation.created_at,
                    updated_at=conversation.updated_at,
                    version=conversation.version,
                )
            )
        return conversation

    def get(self, conversation_id: str) -> Conversation | None:
        with self.database.session() as session:
            row = session.get(ConversationRow, conversation_id)
            return self._conversation(row) if row else None

    def append_message(self, message: ConversationMessage) -> ConversationMessage:
        with self.database.session() as session:
            conversation = session.get(ConversationRow, message.conversation_id)
            if conversation is None:
                raise ResourceNotFoundError(
                    "conversation not found",
                    details={"conversation_id": message.conversation_id},
                )
            if message.request_id:
                existing = session.execute(
                    select(ConversationMessageRow).where(
                        ConversationMessageRow.conversation_id == message.conversation_id,
                        ConversationMessageRow.request_id == message.request_id,
                        ConversationMessageRow.role == message.role,
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    if existing.content != message.content:
                        raise ConflictError(
                            "message request id already exists with different content",
                            details={"request_id": message.request_id},
                        )
                    return self._message(existing)

            last_sequence = session.execute(
                select(ConversationMessageRow.sequence_no)
                .where(
                    ConversationMessageRow.conversation_id
                    == message.conversation_id
                )
                .order_by(ConversationMessageRow.sequence_no.desc())
                .limit(1)
            ).scalar_one_or_none()
            message.sequence_no = (last_sequence or 0) + 1
            session.add(
                ConversationMessageRow(
                    message_id=message.message_id,
                    conversation_id=message.conversation_id,
                    sequence_no=message.sequence_no,
                    role=message.role,
                    content=message.content,
                    request_id=message.request_id,
                    token_count=message.token_count,
                    created_at=message.created_at,
                )
            )
            conversation.updated_at = message.created_at
            conversation.version += 1
        return message

    def list_messages(
        self,
        conversation_id: str,
        *,
        after_sequence: int = 0,
        limit: int | None = None,
    ) -> list[ConversationMessage]:
        with self.database.session() as session:
            statement = (
                select(ConversationMessageRow)
                .where(
                    ConversationMessageRow.conversation_id == conversation_id,
                    ConversationMessageRow.sequence_no > after_sequence,
                )
                .order_by(ConversationMessageRow.sequence_no)
            )
            if limit is not None:
                statement = statement.limit(limit)
            return [self._message(row) for row in session.execute(statement).scalars()]

    def list_recent_messages(
        self,
        conversation_id: str,
        *,
        limit: int,
        after_sequence: int = 0,
    ) -> list[ConversationMessage]:
        with self.database.session() as session:
            rows = list(
                session.execute(
                    select(ConversationMessageRow)
                    .where(
                        ConversationMessageRow.conversation_id == conversation_id,
                        ConversationMessageRow.sequence_no > after_sequence,
                    )
                    .order_by(ConversationMessageRow.sequence_no.desc())
                    .limit(limit)
                ).scalars()
            )
            return [self._message(row) for row in reversed(rows)]

    def upsert_summary(self, summary: ConversationSummary) -> ConversationSummary:
        with self.database.session() as session:
            row = session.get(ConversationSummaryRow, summary.conversation_id)
            if row is not None and summary.through_sequence < row.through_sequence:
                raise ConflictError(
                    "conversation summary cannot move backwards",
                    details={"conversation_id": summary.conversation_id},
                )
            if row is None:
                session.add(
                    ConversationSummaryRow(
                        conversation_id=summary.conversation_id,
                        summary_version=summary.summary_version,
                        through_sequence=summary.through_sequence,
                        payload=summary.payload,
                        updated_at=summary.updated_at,
                    )
                )
            else:
                row.summary_version = summary.summary_version
                row.through_sequence = summary.through_sequence
                row.payload = summary.payload
                row.updated_at = summary.updated_at
        return summary

    def get_summary(self, conversation_id: str) -> ConversationSummary | None:
        with self.database.session() as session:
            row = session.get(ConversationSummaryRow, conversation_id)
            if row is None:
                return None
            return ConversationSummary(
                conversation_id=row.conversation_id,
                summary_version=row.summary_version,
                through_sequence=row.through_sequence,
                payload=dict(row.payload),
                updated_at=row.updated_at,
            )

    def delete(self, conversation_id: str) -> bool:
        with self.database.session() as session:
            row = session.get(ConversationRow, conversation_id)
            if row is None:
                return False
            session.delete(row)
            return True
