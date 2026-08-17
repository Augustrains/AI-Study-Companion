from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Protocol

from modules.conversation.models import ConversationMessage, ConversationSummary
from modules.conversation.service import ConversationService


class SummaryBackend(Protocol):
    def summarize(
        self,
        existing: dict[str, Any],
        messages: list[ConversationMessage],
    ) -> dict[str, Any]: ...


class RuleBasedSummaryBackend:
    """Safe deterministic fallback; summaries never become mastery evidence."""

    def summarize(
        self,
        existing: dict[str, Any],
        messages: list[ConversationMessage],
    ) -> dict[str, Any]:
        topics = deque(existing.get("topics", []), maxlen=12)
        assistant_notes = deque(existing.get("assistant_notes", []), maxlen=8)
        confusions = deque(existing.get("open_confusions", []), maxlen=8)
        preferences = deque(existing.get("explicit_preferences", []), maxlen=8)
        last_intent = str(existing.get("last_intent", ""))

        for message in messages:
            text = " ".join(message.content.split())[:320]
            if not text:
                continue
            if message.role == "user":
                last_intent = text
                if text not in topics:
                    topics.append(text)
                if any(
                    marker in text
                    for marker in ("不懂", "不会", "困惑", "为什么", "?", "？")
                ):
                    confusions.append(text)
                if any(
                    marker in text for marker in ("我喜欢", "我希望", "请用", "偏好")
                ):
                    preferences.append(text)
            elif message.role == "assistant":
                assistant_notes.append(text)

        return {
            "topics": list(topics),
            "resolved_questions": list(existing.get("resolved_questions", []))[-8:],
            "assistant_notes": list(assistant_notes),
            "open_confusions": list(confusions),
            "explicit_preferences": list(preferences),
            "pending_tasks": list(existing.get("pending_tasks", []))[-8:],
            "last_intent": last_intent,
        }


@dataclass
class ConversationSummaryManager:
    service: ConversationService
    backend: SummaryBackend

    def refresh_if_needed(
        self,
        conversation_id: str,
        *,
        actor_user_id: str,
        trigger_messages: int,
        keep_recent: int,
    ) -> ConversationSummary | None:
        existing = self.service.summary(
            conversation_id,
            actor_user_id=actor_user_id,
        )
        through = existing.through_sequence if existing else 0
        messages = self.service.messages(
            conversation_id,
            actor_user_id=actor_user_id,
            after_sequence=through,
        )
        if trigger_messages <= 0 or len(messages) <= trigger_messages:
            return existing
        summarize_count = max(0, len(messages) - keep_recent)
        if summarize_count == 0:
            return existing
        selected = messages[:summarize_count]
        payload = self.backend.summarize(existing.payload if existing else {}, selected)
        summary = ConversationSummary(
            conversation_id=conversation_id,
            summary_version=(existing.summary_version if existing else 0) + 1,
            through_sequence=selected[-1].sequence_no,
            payload=payload,
            updated_at=self.service.repository.now(),
        )
        return self.service.save_summary(summary, actor_user_id=actor_user_id)
