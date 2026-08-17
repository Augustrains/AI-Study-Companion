from __future__ import annotations

from modules.persistence.database import Database
from modules.persistence.tables import ContextTraceRow

from .models import ContextEnvelope


class ContextTraceRepository:
    """Persist trace metadata without storing the full prompt or user secrets."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def save(self, envelope: ContextEnvelope) -> None:
        with self.database.session() as session:
            session.add(
                ContextTraceRow(
                    context_id=envelope.identity.context_id,
                    request_id=envelope.identity.request_id,
                    user_id=envelope.identity.user_id,
                    conversation_id=envelope.identity.conversation_id,
                    mode=envelope.identity.mode,
                    policy_version=envelope.constraints.policy_version,
                    source_versions=envelope.trace.source_versions,
                    selected_message_range=envelope.trace.selected_message_range,
                    estimated_tokens=envelope.trace.estimated_tokens,
                    created_at=envelope.trace.created_at,
                )
            )
