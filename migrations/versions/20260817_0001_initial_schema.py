"""Create the initial application schema.

Revision ID: 20260817_0001
Revises:
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260817_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learner_memory_states",
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("learning_domain", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "learning_domain"),
    )
    op.create_table(
        "memory_events",
        sa.Column("event_id", sa.String(length=200), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("learning_domain", sa.String(length=128), nullable=False),
        sa.Column("knowledge_point_id", sa.String(length=200), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("algorithm_version", sa.String(length=80), nullable=False),
        sa.Column("occurred_at", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_memory_events_owner",
        "memory_events",
        ["user_id", "learning_domain", "occurred_at"],
        unique=False,
    )
    op.create_table(
        "learner_memory_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("learning_domain", sa.String(length=128), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(length=200), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "learning_domain",
            "state_version",
            name="uq_memory_history_version",
        ),
    )
    op.create_table(
        "migration_ledger",
        sa.Column("migration_name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("completed_at", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("migration_name", "version"),
    )
    op.create_table(
        "conversations",
        sa.Column("conversation_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("book_id", sa.String(length=128), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("conversation_id"),
    )
    op.create_index(
        "ix_conversations_owner",
        "conversations",
        ["user_id", "book_id", "updated_at"],
        unique=False,
    )
    op.create_table(
        "conversation_turns",
        sa.Column("conversation_id", sa.String(length=128), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("book_id", sa.String(length=128), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("execution_token", sa.String(length=128), nullable=False),
        sa.Column("lease_expires_at", sa.String(length=64), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.conversation_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("conversation_id", "request_id"),
        sa.UniqueConstraint(
            "conversation_id",
            "request_id",
            name="uq_conversation_turn_request",
        ),
    )
    op.create_index(
        "ix_conversation_turn_owner",
        "conversation_turns",
        ["user_id", "book_id", "updated_at"],
        unique=False,
    )
    op.create_table(
        "conversation_messages",
        sa.Column("message_id", sa.String(length=128), nullable=False),
        sa.Column("conversation_id", sa.String(length=128), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.conversation_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("message_id"),
        sa.UniqueConstraint(
            "conversation_id",
            "request_id",
            "role",
            name="uq_message_request_role",
        ),
        sa.UniqueConstraint(
            "conversation_id",
            "sequence_no",
            name="uq_message_sequence",
        ),
    )
    op.create_index(
        "ix_messages_conversation",
        "conversation_messages",
        ["conversation_id", "sequence_no"],
        unique=False,
    )
    op.create_table(
        "conversation_summaries",
        sa.Column("conversation_id", sa.String(length=128), nullable=False),
        sa.Column("summary_version", sa.Integer(), nullable=False),
        sa.Column("through_sequence", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.conversation_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("conversation_id"),
    )
    op.create_table(
        "workflow_sessions",
        sa.Column("workflow_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("workflow_type", sa.String(length=32), nullable=False),
        sa.Column("learning_domain", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("workflow_id"),
    )
    op.create_index(
        "ix_workflow_owner",
        "workflow_sessions",
        ["user_id", "workflow_type", "updated_at"],
        unique=False,
    )
    op.create_table(
        "context_traces",
        sa.Column("context_id", sa.String(length=128), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("conversation_id", sa.String(length=128), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("policy_version", sa.String(length=32), nullable=False),
        sa.Column("source_versions", sa.JSON(), nullable=False),
        sa.Column("selected_message_range", sa.JSON(), nullable=False),
        sa.Column("estimated_tokens", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("context_id"),
    )
    op.create_table(
        "diagnosis_results",
        sa.Column("diagnosis_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("book_id", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("diagnosis_id"),
    )
    op.create_index(
        "ix_diagnosis_results_owner",
        "diagnosis_results",
        ["user_id", "book_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_diagnosis_results_owner", table_name="diagnosis_results")
    op.drop_table("diagnosis_results")
    op.drop_table("context_traces")
    op.drop_index("ix_workflow_owner", table_name="workflow_sessions")
    op.drop_table("workflow_sessions")
    op.drop_table("conversation_summaries")
    op.drop_index("ix_messages_conversation", table_name="conversation_messages")
    op.drop_table("conversation_messages")
    op.drop_index("ix_conversation_turn_owner", table_name="conversation_turns")
    op.drop_table("conversation_turns")
    op.drop_index("ix_conversations_owner", table_name="conversations")
    op.drop_table("conversations")
    op.drop_table("migration_ledger")
    op.drop_table("learner_memory_history")
    op.drop_index("ix_memory_events_owner", table_name="memory_events")
    op.drop_table("memory_events")
    op.drop_table("learner_memory_states")
