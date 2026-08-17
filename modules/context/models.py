from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from modules.common import api as common_api


class ContextMode(StrEnum):
    PROFILE = "profile"
    DIAGNOSIS = "diagnosis"
    PLANNING = "planning"
    TUTOR = "tutor"
    REVIEW = "review"


@dataclass
class ContextIdentity:
    context_id: str
    request_id: str
    user_id: str
    book_id: str
    mode: str
    conversation_id: str | None = None


@dataclass
class MasteryContext:
    knowledge_point_id: str
    assessed_mastery_level: str
    user_calibrated_level: str | None
    effective_mastery_level: str
    mastery_score: float
    confidence: float
    memory_status: str
    memory_stability_days: float
    next_review_at: str | None
    evidence_ids: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    algorithm_name: str = ""
    algorithm_version: str = ""
    source: str = ""


@dataclass
class LearnerContext:
    verified_mastery: list[MasteryContext] = field(default_factory=list)
    preferences: dict[str, Any] = field(default_factory=dict)
    current_confusions: str = ""
    learning_goals: list[str] = field(default_factory=list)
    self_assessed_level: str = "unknown"
    self_reported_known_knowledge_point_ids: list[str] = field(default_factory=list)
    self_reported_unknown_knowledge_point_ids: list[str] = field(default_factory=list)
    self_reported_knowledge_point_note: str = ""


@dataclass
class WorkflowContext:
    learning_goal: str = ""
    current_task: dict[str, Any] = field(default_factory=dict)
    diagnosis_summary: dict[str, Any] = field(default_factory=dict)
    workflow_state: dict[str, Any] = field(default_factory=dict)
    relevant_knowledge_point_ids: list[str] = field(default_factory=list)


@dataclass
class ContextMessage:
    message_id: str
    sequence_no: int
    role: str
    content: str
    created_at: str


@dataclass
class ConversationContext:
    summary: dict[str, Any] = field(default_factory=dict)
    summary_version: int = 0
    summary_through_sequence: int = 0
    recent_messages: list[ContextMessage] = field(default_factory=list)


@dataclass
class ContextConstraints:
    policy_version: str
    forbidden_fields: list[str] = field(default_factory=list)
    max_context_tokens: int = 0
    response_reserve_tokens: int = 0
    current_input_must_be_preserved: bool = True
    untrusted_data: bool = True


@dataclass
class ContextTrace:
    source_versions: dict[str, Any] = field(default_factory=dict)
    selected_message_range: dict[str, int] = field(default_factory=dict)
    estimated_tokens: int = 0
    truncated: bool = False
    created_at: str = ""


@dataclass
class ContextEnvelope:
    identity: ContextIdentity
    current_input: str
    learner: LearnerContext
    workflow: WorkflowContext
    conversation: ConversationContext
    constraints: ContextConstraints
    trace: ContextTrace

    def to_dict(self) -> dict[str, Any]:
        return common_api.serialization.to_data(self)
