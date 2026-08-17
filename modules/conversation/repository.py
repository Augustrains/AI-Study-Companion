from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from modules.common.errors import ConflictError, ResourceNotFoundError
from modules.persistence.database import Database
from modules.persistence.tables import (
    ConversationMessageRow,
    ConversationRow,
    ConversationSummaryRow,
    ConversationTurnRow,
)

from .models import (
    Conversation,
    ConversationMessage,
    ConversationSummary,
    ConversationTurn,
)


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

    @staticmethod
    def _turn(row: ConversationTurnRow) -> ConversationTurn:
        return ConversationTurn(
            conversation_id=row.conversation_id,
            request_id=row.request_id,
            user_id=row.user_id,
            book_id=row.book_id,
            question=row.question,
            status=row.status,
            response=dict(row.response),
            execution_token=row.execution_token,
            lease_expires_at=row.lease_expires_at,
            attempt_count=row.attempt_count,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _begin_write(self, session) -> None:
        if self.database.engine.dialect.name.startswith("sqlite"):
            session.execute(text("BEGIN IMMEDIATE"))

    def _owned_conversation_row(
        self,
        session,
        *,
        conversation_id: str,
        actor_user_id: str,
        book_id: str,
    ) -> ConversationRow:
        statement = select(ConversationRow).where(
            ConversationRow.conversation_id == conversation_id
        )
        if not self.database.engine.dialect.name.startswith("sqlite"):
            statement = statement.with_for_update()
        row = session.execute(statement).scalar_one_or_none()
        if (
            row is None
            or row.user_id != actor_user_id
            or row.book_id != book_id
        ):
            raise ResourceNotFoundError(
                "conversation not found",
                details={"conversation_id": conversation_id},
            )
        return row

    @staticmethod
    def _owned_turn_row(
        session,
        *,
        conversation_id: str,
        request_id: str,
        actor_user_id: str,
        book_id: str,
        lock: bool,
        sqlite: bool,
    ) -> ConversationTurnRow:
        statement = select(ConversationTurnRow).where(
            ConversationTurnRow.conversation_id == conversation_id,
            ConversationTurnRow.request_id == request_id,
        )
        if lock and not sqlite:
            statement = statement.with_for_update()
        row = session.execute(statement).scalar_one_or_none()
        if (
            row is None
            or row.user_id != actor_user_id
            or row.book_id != book_id
        ):
            raise ResourceNotFoundError(
                "conversation turn not found",
                details={
                    "conversation_id": conversation_id,
                    "request_id": request_id,
                },
            )
        return row

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

    def begin_turn(self, turn: ConversationTurn) -> ConversationTurn:
        """Create a pending turn or return its same-question duplicate."""

        try:
            with self.database.session() as session:
                self._begin_write(session)
                self._owned_conversation_row(
                    session,
                    conversation_id=turn.conversation_id,
                    actor_user_id=turn.user_id,
                    book_id=turn.book_id,
                )
                existing = session.get(
                    ConversationTurnRow,
                    (turn.conversation_id, turn.request_id),
                )
                if existing is not None:
                    if (
                        existing.user_id != turn.user_id
                        or existing.book_id != turn.book_id
                    ):
                        raise ResourceNotFoundError(
                            "conversation turn not found",
                            details={
                                "conversation_id": turn.conversation_id,
                                "request_id": turn.request_id,
                            },
                        )
                    if existing.question != turn.question:
                        raise ConflictError(
                            "conversation turn request id has a different question",
                            details={
                                "conversation_id": turn.conversation_id,
                                "request_id": turn.request_id,
                            },
                        )
                    return self._turn(existing)
                session.add(
                    ConversationTurnRow(
                        conversation_id=turn.conversation_id,
                        request_id=turn.request_id,
                        user_id=turn.user_id,
                        book_id=turn.book_id,
                        question=turn.question,
                        status=turn.status,
                        response=turn.response,
                        execution_token=turn.execution_token,
                        lease_expires_at=turn.lease_expires_at,
                        attempt_count=turn.attempt_count,
                        created_at=turn.created_at,
                        updated_at=turn.updated_at,
                    )
                )
            return turn
        except IntegrityError as exc:
            # Normalize a cross-process insert race into idempotent reuse or a
            # domain conflict; callers must never receive SQLAlchemy details.
            existing = self.get_turn(turn.conversation_id, turn.request_id)
            if (
                existing is not None
                and existing.user_id == turn.user_id
                and existing.book_id == turn.book_id
            ):
                if existing.question == turn.question:
                    return existing
                raise ConflictError(
                    "conversation turn request id has a different question",
                    details={
                        "conversation_id": turn.conversation_id,
                        "request_id": turn.request_id,
                    },
                    cause=exc,
                ) from exc
            raise ConflictError(
                "conversation turn conflicted with a concurrent write",
                details={
                    "conversation_id": turn.conversation_id,
                    "request_id": turn.request_id,
                },
                cause=exc,
            ) from exc

    def get_turn(
        self,
        conversation_id: str,
        request_id: str,
    ) -> ConversationTurn | None:
        with self.database.session() as session:
            row = session.get(
                ConversationTurnRow,
                (conversation_id, request_id),
            )
            return self._turn(row) if row is not None else None

    def claim_turn(
        self,
        *,
        conversation_id: str,
        request_id: str,
        actor_user_id: str,
        book_id: str,
        execution_token: str,
        lease_expires_at: str,
        updated_at: str,
    ) -> ConversationTurn:
        """Atomically claim a retryable turn for one execution lease."""

        try:
            with self.database.session() as session:
                self._begin_write(session)
                self._owned_conversation_row(
                    session,
                    conversation_id=conversation_id,
                    actor_user_id=actor_user_id,
                    book_id=book_id,
                )
                row = self._owned_turn_row(
                    session,
                    conversation_id=conversation_id,
                    request_id=request_id,
                    actor_user_id=actor_user_id,
                    book_id=book_id,
                    lock=True,
                    sqlite=self.database.engine.dialect.name.startswith("sqlite"),
                )
                if row.status == "completed":
                    return self._turn(row)
                if (
                    row.status == "pending"
                    and row.execution_token
                    and row.execution_token != execution_token
                    and self._lease_is_active(row.lease_expires_at, updated_at)
                ):
                    raise ConflictError(
                        "conversation turn is already in progress",
                        details={
                            "conversation_id": conversation_id,
                            "request_id": request_id,
                            "lease_expires_at": row.lease_expires_at,
                        },
                    )
                row.status = "pending"
                row.response = {}
                row.execution_token = execution_token
                row.lease_expires_at = lease_expires_at
                row.attempt_count += 1
                row.updated_at = updated_at
                return self._turn(row)
        except IntegrityError as exc:
            raise ConflictError(
                "conversation turn conflicted with a concurrent claim",
                details={
                    "conversation_id": conversation_id,
                    "request_id": request_id,
                },
                cause=exc,
            ) from exc

    def complete_turn(
        self,
        *,
        conversation_id: str,
        request_id: str,
        actor_user_id: str,
        book_id: str,
        response: dict[str, object],
        updated_at: str,
        execution_token: str = "",
    ) -> ConversationTurn:
        return self._transition_turn(
            conversation_id=conversation_id,
            request_id=request_id,
            actor_user_id=actor_user_id,
            book_id=book_id,
            status="completed",
            response=response,
            updated_at=updated_at,
            execution_token=execution_token,
        )

    def fail_turn(
        self,
        *,
        conversation_id: str,
        request_id: str,
        actor_user_id: str,
        book_id: str,
        response: dict[str, object],
        updated_at: str,
        execution_token: str = "",
    ) -> ConversationTurn:
        return self._transition_turn(
            conversation_id=conversation_id,
            request_id=request_id,
            actor_user_id=actor_user_id,
            book_id=book_id,
            status="failed",
            response=response,
            updated_at=updated_at,
            execution_token=execution_token,
        )

    def _transition_turn(
        self,
        *,
        conversation_id: str,
        request_id: str,
        actor_user_id: str,
        book_id: str,
        status: str,
        response: dict[str, object],
        updated_at: str,
        execution_token: str,
    ) -> ConversationTurn:
        try:
            with self.database.session() as session:
                self._begin_write(session)
                self._owned_conversation_row(
                    session,
                    conversation_id=conversation_id,
                    actor_user_id=actor_user_id,
                    book_id=book_id,
                )
                row = self._owned_turn_row(
                    session,
                    conversation_id=conversation_id,
                    request_id=request_id,
                    actor_user_id=actor_user_id,
                    book_id=book_id,
                    lock=True,
                    sqlite=self.database.engine.dialect.name.startswith("sqlite"),
                )
                if row.status == "completed":
                    if status == "failed" or row.response == response:
                        return self._turn(row)
                    raise ConflictError(
                        "completed conversation turn has a different response",
                        details={
                            "conversation_id": conversation_id,
                            "request_id": request_id,
                        },
                    )
                if row.execution_token and row.execution_token != execution_token:
                    raise ConflictError(
                        "conversation turn execution lease is not owned",
                        details={
                            "conversation_id": conversation_id,
                            "request_id": request_id,
                        },
                    )
                row.status = status
                row.response = response
                row.execution_token = ""
                row.lease_expires_at = ""
                row.updated_at = updated_at
                return self._turn(row)
        except IntegrityError as exc:
            raise ConflictError(
                "conversation turn conflicted with a concurrent transition",
                details={
                    "conversation_id": conversation_id,
                    "request_id": request_id,
                },
                cause=exc,
            ) from exc

    @staticmethod
    def _lease_is_active(lease_expires_at: str, now: str) -> bool:
        if not lease_expires_at:
            return False
        try:
            return datetime.fromisoformat(lease_expires_at) > datetime.fromisoformat(now)
        except ValueError:
            # An unparseable non-empty lease is treated as active so a corrupt
            # record cannot permit two executions.
            return True

    def append_message(self, message: ConversationMessage) -> ConversationMessage:
        try:
            with self.database.session() as session:
                if self.database.engine.dialect.name.startswith("sqlite"):
                    session.execute(text("BEGIN IMMEDIATE"))
                statement = select(ConversationRow).where(
                    ConversationRow.conversation_id == message.conversation_id
                )
                if not self.database.engine.dialect.name.startswith("sqlite"):
                    statement = statement.with_for_update()
                conversation = session.execute(statement).scalar_one_or_none()
                if conversation is None:
                    raise ResourceNotFoundError(
                        "conversation not found",
                        details={"conversation_id": message.conversation_id},
                    )
                if message.request_id:
                    existing = session.execute(
                        select(ConversationMessageRow).where(
                            ConversationMessageRow.conversation_id
                            == message.conversation_id,
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
        except IntegrityError as exc:
            raise ConflictError(
                "conversation message conflicted with a concurrent write",
                details={"conversation_id": message.conversation_id},
                cause=exc,
            ) from exc
        return message

    def append_turn_messages(
        self,
        user_message: ConversationMessage,
        assistant_message: ConversationMessage,
        *,
        actor_user_id: str,
        book_id: str,
    ) -> tuple[ConversationMessage, ConversationMessage]:
        """Atomically append one contiguous user/assistant message pair."""

        if (
            user_message.conversation_id != assistant_message.conversation_id
            or not user_message.request_id
            or user_message.request_id != assistant_message.request_id
            or user_message.role != "user"
            or assistant_message.role != "assistant"
        ):
            raise ConflictError(
                "conversation turn messages must share one request id and order",
                details={
                    "conversation_id": user_message.conversation_id,
                    "request_id": user_message.request_id,
                },
            )
        conversation_id = user_message.conversation_id
        request_id = user_message.request_id
        try:
            with self.database.session() as session:
                self._begin_write(session)
                conversation = self._owned_conversation_row(
                    session,
                    conversation_id=conversation_id,
                    actor_user_id=actor_user_id,
                    book_id=book_id,
                )
                existing = list(
                    session.execute(
                        select(ConversationMessageRow).where(
                            ConversationMessageRow.conversation_id
                            == conversation_id,
                            ConversationMessageRow.request_id == request_id,
                        )
                    ).scalars()
                )
                if existing:
                    return self._match_turn_messages(
                        existing,
                        user_message=user_message,
                        assistant_message=assistant_message,
                    )

                last_sequence = session.execute(
                    select(ConversationMessageRow.sequence_no)
                    .where(
                        ConversationMessageRow.conversation_id == conversation_id
                    )
                    .order_by(ConversationMessageRow.sequence_no.desc())
                    .limit(1)
                ).scalar_one_or_none()
                user_message.sequence_no = (last_sequence or 0) + 1
                assistant_message.sequence_no = user_message.sequence_no + 1
                session.add_all(
                    [
                        self._message_row(user_message),
                        self._message_row(assistant_message),
                    ]
                )
                conversation.updated_at = assistant_message.created_at
                conversation.version += 2
            return user_message, assistant_message
        except IntegrityError as exc:
            # A non-SQLite backend may race at commit after both readers saw
            # no pair. Re-read and resolve a semantically identical winner.
            conversation = self.get(conversation_id)
            if (
                conversation is None
                or conversation.user_id != actor_user_id
                or conversation.book_id != book_id
            ):
                raise ResourceNotFoundError(
                    "conversation not found",
                    details={"conversation_id": conversation_id},
                ) from exc
            with self.database.session() as session:
                existing = list(
                    session.execute(
                        select(ConversationMessageRow).where(
                            ConversationMessageRow.conversation_id
                            == conversation_id,
                            ConversationMessageRow.request_id == request_id,
                        )
                    ).scalars()
                )
            if existing:
                return self._match_turn_messages(
                    existing,
                    user_message=user_message,
                    assistant_message=assistant_message,
                    cause=exc,
                )
            raise ConflictError(
                "conversation turn messages conflicted with a concurrent write",
                details={
                    "conversation_id": conversation_id,
                    "request_id": request_id,
                },
                cause=exc,
            ) from exc

    @staticmethod
    def _message_row(message: ConversationMessage) -> ConversationMessageRow:
        return ConversationMessageRow(
            message_id=message.message_id,
            conversation_id=message.conversation_id,
            sequence_no=message.sequence_no,
            role=message.role,
            content=message.content,
            request_id=message.request_id,
            token_count=message.token_count,
            created_at=message.created_at,
        )

    @classmethod
    def _match_turn_messages(
        cls,
        rows: list[ConversationMessageRow],
        *,
        user_message: ConversationMessage,
        assistant_message: ConversationMessage,
        cause: Exception | None = None,
    ) -> tuple[ConversationMessage, ConversationMessage]:
        by_role = {row.role: row for row in rows}
        if (
            len(rows) == 2
            and set(by_role) == {"user", "assistant"}
            and by_role["user"].content == user_message.content
            and by_role["assistant"].content == assistant_message.content
        ):
            return cls._message(by_role["user"]), cls._message(
                by_role["assistant"]
            )
        raise ConflictError(
            "conversation turn request id has different or incomplete messages",
            details={
                "conversation_id": user_message.conversation_id,
                "request_id": user_message.request_id,
            },
            cause=cause,
        )

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
