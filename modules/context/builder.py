from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from modules.conversation.models import ConversationMessage
from modules.conversation.service import ConversationService
from modules.memory.module import MemoryModule

from .budget import ContextBudget
from .models import (
    ContextConstraints,
    ContextEnvelope,
    ContextIdentity,
    ContextMessage,
    ContextMode,
    ContextTrace,
    ConversationContext,
    LearnerContext,
    MasteryContext,
    WorkflowContext,
)
from .policies import (
    ContextPolicyRegistry,
    assessment_safe_payload,
    sanitize_payload,
)
from .summarizer import ConversationSummaryManager
from .trace import ContextTraceRepository


@dataclass(frozen=True)
class ContextRequest:
    request_id: str
    user_id: str
    book_id: str
    mode: ContextMode | str
    current_input: str = ""
    conversation_id: str | None = None
    learning_goal: str = ""
    current_task: dict[str, Any] = field(default_factory=dict)
    diagnosis_summary: dict[str, Any] = field(default_factory=dict)
    workflow_state: dict[str, Any] = field(default_factory=dict)
    knowledge_point_ids: list[str] = field(default_factory=list)


class ContextBuilder:
    def __init__(
        self,
        *,
        memory: MemoryModule,
        conversations: ConversationService | None = None,
        policies: ContextPolicyRegistry | None = None,
        budget: ContextBudget | None = None,
        summary_manager: ConversationSummaryManager | None = None,
        traces: ContextTraceRepository | None = None,
    ) -> None:
        self.memory = memory
        self.conversations = conversations
        self.policies = policies or ContextPolicyRegistry()
        self.budget = budget or ContextBudget()
        self.summary_manager = summary_manager
        self.traces = traces

    def build(self, request: ContextRequest) -> ContextEnvelope:
        policy = self.policies.get(request.mode)
        now = datetime.now(timezone.utc).isoformat()
        learner_memory = self.memory.get_learner_memory(
            request.user_id,
            request.book_id,
        )
        point_filter = {str(item) for item in request.knowledge_point_ids if item}
        mastery = []
        if policy.include_verified_mastery:
            for point in learner_memory.knowledge_points:
                assessed = point.assessed_mastery_level
                if assessed is None and point.source.startswith("diagnostic:"):
                    assessed = point.mastery_level
                if assessed is None:
                    continue
                if point_filter and point.knowledge_point_id not in point_filter:
                    continue
                mastery.append(
                    MasteryContext(
                        knowledge_point_id=point.knowledge_point_id,
                        assessed_mastery_level=assessed,
                        user_calibrated_level=point.user_calibrated_level,
                        effective_mastery_level=point.user_calibrated_level or assessed,
                        mastery_score=point.mastery_score,
                        confidence=point.confidence,
                        memory_status=point.memory_status,
                        memory_stability_days=point.memory_stability_days,
                        next_review_at=point.next_review_at,
                        evidence_ids=list(point.evidence_ids),
                        reason_codes=list(point.reason_codes),
                        algorithm_name=point.algorithm_name,
                        algorithm_version=point.algorithm_version,
                        source=point.source,
                    )
                )
            mastery.sort(key=lambda item: item.knowledge_point_id)
            mastery = mastery[: policy.max_memory_points]

        learner = LearnerContext(
            verified_mastery=mastery,
            preferences=dict(learner_memory.preferences)
            if policy.include_preferences
            else {},
            current_confusions=(
                learner_memory.current_confusions if policy.include_self_report else ""
            ),
            learning_goals=list(learner_memory.learning_goals),
            self_assessed_level=(
                learner_memory.self_assessed_level
                if policy.include_self_report
                else "unknown"
            ),
            self_reported_known_knowledge_point_ids=(
                list(learner_memory.self_reported_known_knowledge_point_ids)
                if policy.include_self_report
                else []
            ),
            self_reported_unknown_knowledge_point_ids=(
                list(learner_memory.self_reported_unknown_knowledge_point_ids)
                if policy.include_self_report
                else []
            ),
            self_reported_knowledge_point_note=(
                learner_memory.self_reported_knowledge_point_note
                if policy.include_self_report
                else ""
            ),
        )

        conversation_context = ConversationContext()
        conversation_version = 0
        if policy.include_conversation and request.conversation_id:
            if self.conversations is None:
                raise RuntimeError(
                    "conversation service is required for this context mode"
                )
            conversation = self.conversations.require_owned(
                request.conversation_id,
                actor_user_id=request.user_id,
                book_id=request.book_id,
            )
            conversation_version = conversation.version
            summary = None
            if policy.include_summary:
                if self.summary_manager is not None:
                    summary = self.summary_manager.refresh_if_needed(
                        request.conversation_id,
                        actor_user_id=request.user_id,
                        trigger_messages=policy.summary_trigger_messages,
                        keep_recent=policy.max_recent_messages,
                    )
                else:
                    summary = self.conversations.summary(
                        request.conversation_id,
                        actor_user_id=request.user_id,
                    )
            through = summary.through_sequence if summary else 0
            messages = self.conversations.repository.list_recent_messages(
                request.conversation_id,
                limit=policy.max_recent_messages + 1,
                after_sequence=through,
            )
            messages = [
                item
                for item in messages
                if not (
                    request.request_id
                    and item.request_id == request.request_id
                    and item.role == "user"
                )
            ]
            messages = messages[-policy.max_recent_messages :]
            conversation_context = ConversationContext(
                summary=dict(summary.payload) if summary else {},
                summary_version=summary.summary_version if summary else 0,
                summary_through_sequence=through,
                recent_messages=[self._message(item) for item in messages],
            )

        forbidden = policy.forbidden_fields
        is_diagnosis = policy.mode is ContextMode.DIAGNOSIS
        workflow = WorkflowContext(
            learning_goal=request.learning_goal,
            current_task=(
                assessment_safe_payload(request.current_task)
                if is_diagnosis
                else sanitize_payload(request.current_task, forbidden)
            ),
            diagnosis_summary=(
                {}
                if is_diagnosis
                else sanitize_payload(request.diagnosis_summary, forbidden)
            ),
            workflow_state=(
                assessment_safe_payload(request.workflow_state)
                if is_diagnosis
                else sanitize_payload(request.workflow_state, forbidden)
            ),
            relevant_knowledge_point_ids=sorted(point_filter),
        )
        selected = conversation_context.recent_messages
        envelope = ContextEnvelope(
            identity=ContextIdentity(
                context_id=f"ctx-{uuid4().hex[:20]}",
                request_id=request.request_id or f"req-{uuid4().hex[:16]}",
                user_id=request.user_id,
                book_id=request.book_id,
                mode=policy.mode.value,
                conversation_id=request.conversation_id,
            ),
            current_input=request.current_input,
            learner=learner,
            workflow=workflow,
            conversation=conversation_context,
            constraints=ContextConstraints(
                policy_version=policy.version,
                forbidden_fields=list(forbidden),
                max_context_tokens=policy.max_context_tokens,
                response_reserve_tokens=policy.response_reserve_tokens,
            ),
            trace=ContextTrace(
                source_versions={
                    "learner_memory": learner_memory.state_version,
                    "conversation": conversation_version,
                    "conversation_summary": conversation_context.summary_version,
                },
                selected_message_range=(
                    {
                        "from": selected[0].sequence_no,
                        "to": selected[-1].sequence_no,
                    }
                    if selected
                    else {}
                ),
                created_at=now,
            ),
        )
        envelope = self.budget.fit(envelope)
        if self.traces is not None:
            self.traces.save(envelope)
        return envelope

    @staticmethod
    def _message(message: ConversationMessage) -> ContextMessage:
        return ContextMessage(
            message_id=message.message_id,
            sequence_no=message.sequence_no,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
        )

    def for_diagnosis(self, **kwargs: Any) -> ContextEnvelope:
        return self.build(ContextRequest(mode=ContextMode.DIAGNOSIS, **kwargs))

    def for_planning(self, **kwargs: Any) -> ContextEnvelope:
        return self.build(ContextRequest(mode=ContextMode.PLANNING, **kwargs))

    def for_tutor(self, **kwargs: Any) -> ContextEnvelope:
        return self.build(ContextRequest(mode=ContextMode.TUTOR, **kwargs))
