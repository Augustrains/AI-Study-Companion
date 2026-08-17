from __future__ import annotations

from typing import Any

from sqlalchemy import (
    JSON,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class LearnerMemoryStateRow(Base):
    __tablename__ = "learner_memory_states"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    learning_domain: Mapped[str] = mapped_column(String(128), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)


class MemoryEventRow(Base):
    __tablename__ = "memory_events"

    event_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    learning_domain: Mapped[str] = mapped_column(String(128), nullable=False)
    knowledge_point_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(
        String(80), nullable=False, default=""
    )
    occurred_at: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        Index("ix_memory_events_owner", "user_id", "learning_domain", "occurred_at"),
    )


class LearnerMemoryHistoryRow(Base):
    __tablename__ = "learner_memory_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    learning_domain: Mapped[str] = mapped_column(String(128), nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "learning_domain",
            "state_version",
            name="uq_memory_history_version",
        ),
    )


class MigrationLedgerRow(Base):
    """One row means that one versioned data migration completed successfully."""

    __tablename__ = "migration_ledger"

    migration_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    completed_at: Mapped[str] = mapped_column(String(64), nullable=False)


class ConversationRow(Base):
    __tablename__ = "conversations"

    conversation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    book_id: Mapped[str] = mapped_column(String(128), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        Index("ix_conversations_owner", "user_id", "book_id", "updated_at"),
    )


class ConversationTurnRow(Base):
    __tablename__ = "conversation_turns"

    conversation_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
        primary_key=True,
    )
    request_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    book_id: Mapped[str] = mapped_column(String(128), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    execution_token: Mapped[str] = mapped_column(
        String(128), nullable=False, default=""
    )
    lease_expires_at: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "request_id",
            name="uq_conversation_turn_request",
        ),
        Index(
            "ix_conversation_turn_owner",
            "user_id",
            "book_id",
            "updated_at",
        ),
    )


class ConversationMessageRow(Base):
    __tablename__ = "conversation_messages"

    message_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence_no", name="uq_message_sequence"),
        UniqueConstraint(
            "conversation_id",
            "request_id",
            "role",
            name="uq_message_request_role",
        ),
        Index("ix_messages_conversation", "conversation_id", "sequence_no"),
    )


class ConversationSummaryRow(Base):
    __tablename__ = "conversation_summaries"

    conversation_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
        primary_key=True,
    )
    summary_version: Mapped[int] = mapped_column(Integer, nullable=False)
    through_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)


class WorkflowSessionRow(Base):
    __tablename__ = "workflow_sessions"

    workflow_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    workflow_type: Mapped[str] = mapped_column(String(32), nullable=False)
    learning_domain: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        Index("ix_workflow_owner", "user_id", "workflow_type", "updated_at"),
    )


class ContextTraceRow(Base):
    __tablename__ = "context_traces"

    context_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    source_versions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    selected_message_range: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    estimated_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)


class DiagnosisResultRow(Base):
    __tablename__ = "diagnosis_results"

    diagnosis_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    book_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        Index("ix_diagnosis_results_owner", "user_id", "book_id", "updated_at"),
    )
