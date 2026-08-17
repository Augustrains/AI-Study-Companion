from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

MessageRole = Literal["system", "user", "assistant", "tool"]
TurnStatus = Literal["pending", "completed", "failed"]
TURN_STATUSES = ("pending", "completed", "failed")


@dataclass
class Conversation:
    conversation_id: str
    user_id: str
    book_id: str
    mode: str
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""
    version: int = 1


@dataclass
class ConversationMessage:
    message_id: str
    conversation_id: str
    sequence_no: int
    role: MessageRole
    content: str
    request_id: str | None = None
    token_count: int = 0
    created_at: str = ""


@dataclass
class ConversationSummary:
    conversation_id: str
    summary_version: int
    through_sequence: int
    payload: dict[str, Any] = field(default_factory=dict)
    updated_at: str = ""


@dataclass
class ConversationTurn:
    """Durable idempotency record for one question-answer request."""

    conversation_id: str
    request_id: str
    user_id: str
    book_id: str
    question: str
    status: TurnStatus = "pending"
    response: dict[str, Any] = field(default_factory=dict)
    execution_token: str = ""
    lease_expires_at: str = ""
    attempt_count: int = 0
    created_at: str = ""
    updated_at: str = ""
