from __future__ import annotations

import json
from typing import Any

from modules.common.errors import ValidationAppError

from .models import ContextEnvelope


class ConservativeTokenCounter:
    """UTF-8 byte upper bound; replace with a model tokenizer when available."""

    def count_text(self, text: str) -> int:
        return len(text.encode("utf-8"))

    def count(self, value: Any) -> int:
        if isinstance(value, str):
            return self.count_text(value)
        return self.count_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        )


class ContextBudget:
    def __init__(self, counter: ConservativeTokenCounter | None = None) -> None:
        self.counter = counter or ConservativeTokenCounter()

    def fit(
        self, envelope: ContextEnvelope, *, fixed_text: str = ""
    ) -> ContextEnvelope:
        available = (
            envelope.constraints.max_context_tokens
            - envelope.constraints.response_reserve_tokens
        )
        fixed_tokens = self.counter.count_text(fixed_text)
        available_for_envelope = available - fixed_tokens
        if self.counter.count(envelope.current_input) > available_for_envelope:
            raise ValidationAppError(
                "current input exceeds context budget",
                details={"available_tokens": available_for_envelope},
            )

        truncated = False
        while (
            self.counter.count(envelope.to_dict()) > available_for_envelope
            and envelope.conversation.recent_messages
        ):
            envelope.conversation.recent_messages.pop(0)
            truncated = True
        while (
            self.counter.count(envelope.to_dict()) > available_for_envelope
            and len(envelope.learner.verified_mastery) > 1
        ):
            envelope.learner.verified_mastery.pop()
            truncated = True
        if (
            self.counter.count(envelope.to_dict()) > available_for_envelope
            and envelope.conversation.summary
        ):
            envelope.conversation.summary = self._truncate_payload(
                envelope.conversation.summary,
                max_tokens=max(64, available_for_envelope // 5),
            )
            truncated = True

        selected = envelope.conversation.recent_messages
        envelope.trace.selected_message_range = (
            {"from": selected[0].sequence_no, "to": selected[-1].sequence_no}
            if selected
            else {}
        )
        for _ in range(2):
            envelope.trace.estimated_tokens = fixed_tokens + self.counter.count(
                envelope.to_dict()
            )
        envelope.trace.truncated = truncated
        if envelope.trace.estimated_tokens > available:
            raise ValidationAppError(
                "required context exceeds context budget",
                details={
                    "estimated_tokens": envelope.trace.estimated_tokens,
                    "available_tokens": available,
                },
            )
        return envelope

    def _truncate_payload(
        self, payload: dict[str, Any], *, max_tokens: int
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        used = 0
        for key, value in payload.items():
            item_tokens = self.counter.count({key: value})
            if used + item_tokens <= max_tokens:
                result[key] = value
                used += item_tokens
                continue
            if isinstance(value, list):
                kept = []
                for item in value:
                    cost = self.counter.count(item)
                    if used + cost > max_tokens:
                        break
                    kept.append(item)
                    used += cost
                result[key] = kept
            elif isinstance(value, str):
                remaining = max(0, max_tokens - used)
                result[key] = value[: remaining * 2]
            break
        return result
