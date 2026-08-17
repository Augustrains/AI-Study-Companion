from __future__ import annotations

import json
from copy import deepcopy
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

        truncated = envelope.trace.truncated
        while (
            self.counter.count(envelope.to_dict()) > available_for_envelope
            and envelope.learner.verified_mastery
        ):
            # Callers order mastery from most to least relevant.  Removing from
            # the tail therefore protects the points most useful to this turn.
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
        while (
            self.counter.count(envelope.to_dict()) > available_for_envelope
            and envelope.conversation.recent_messages
        ):
            # Recent turns are higher-value tutor context than broad learner
            # memory or an old summary, so they are the final optional field
            # removed from an envelope.
            envelope.conversation.recent_messages.pop(0)
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

    def fit_prompt(
        self,
        envelope: ContextEnvelope,
        *,
        fixed_text: str,
        additional_untrusted_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Fit the complete Agent input, including retrieval-time data.

        ContextBuilder cannot account for RAG results because retrieval happens
        later.  This second boundary keeps retrieval independent while applying
        one final budget to the system instructions, learner/conversation
        context, retrieved chunks, and the preserved current question.
        """

        external = deepcopy(additional_untrusted_data or {})
        available = (
            envelope.constraints.max_context_tokens
            - envelope.constraints.response_reserve_tokens
        )
        fixed_tokens = self.counter.count_text(fixed_text)
        if fixed_tokens + self.counter.count(envelope.current_input) > available:
            raise ValidationAppError(
                "current input exceeds context budget",
                details={"available_tokens": available - fixed_tokens},
            )

        def estimated() -> int:
            # Counting the complete internal envelope is intentionally more
            # conservative than the public LLM projection used by the renderer.
            return (
                fixed_tokens
                + self.counter.count(envelope.to_dict())
                + self.counter.count(external)
            )

        truncated = envelope.trace.truncated

        # Mastery is pre-ordered from most to least relevant by the workflow.
        # Keep recent dialogue intact while removing low-relevance points.
        while (
            estimated() > available
            and len(envelope.learner.verified_mastery) > 1
        ):
            envelope.learner.verified_mastery.pop()
            truncated = True

        if estimated() > available and envelope.conversation.summary:
            envelope.conversation.summary = self._truncate_payload(
                envelope.conversation.summary,
                max_tokens=max(64, available // 8),
            )
            truncated = True

        chunks = external.get("retrieval_chunks")
        if isinstance(chunks, list):
            # Retriever ranking is preserved: discard lowest-ranked chunks
            # first, without changing retrieval or index behavior.
            while estimated() > available and len(chunks) > 1:
                chunks.pop()
                truncated = True
            if estimated() > available and chunks and isinstance(chunks[0], dict):
                text = chunks[0].get("text")
                if isinstance(text, str) and text:
                    overflow = estimated() - available
                    encoded = text.encode("utf-8")
                    target = max(0, len(encoded) - overflow - 16)
                    chunks[0]["text"] = encoded[:target].decode(
                        "utf-8", errors="ignore"
                    )
                    if not chunks[0]["text"]:
                        chunks.clear()
                    truncated = True

        # A relevant mastery point is useful, but never more important than
        # preserving the recent dialogue needed to understand a follow-up.
        if estimated() > available and envelope.learner.verified_mastery:
            envelope.learner.verified_mastery.pop()
            truncated = True

        # Only pathological inputs reach this stage.  Preserve the newest
        # turns and remove the oldest one at a time.
        while estimated() > available and envelope.conversation.recent_messages:
            envelope.conversation.recent_messages.pop(0)
            truncated = True

        selected = envelope.conversation.recent_messages
        envelope.trace.selected_message_range = (
            {"from": selected[0].sequence_no, "to": selected[-1].sequence_no}
            if selected
            else {}
        )
        envelope.trace.truncated = truncated
        envelope.trace.estimated_tokens = estimated()
        if envelope.trace.estimated_tokens > available:
            raise ValidationAppError(
                "required context exceeds context budget",
                details={
                    "estimated_tokens": envelope.trace.estimated_tokens,
                    "available_tokens": available,
                },
            )
        return external

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
