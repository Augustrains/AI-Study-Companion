from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modules.common.errors import ValidationAppError

from .models import ContextMode

ASSESSMENT_SECRET_FIELDS = (
    "correct_answer",
    "correct_answers",
    "answer_key",
    "solution",
    "reference_answer",
)

ASSESSMENT_SAFE_FIELDS = {
    "id",
    "diagnosisid",
    "question",
    "questionid",
    "title",
    "prompt",
    "text",
    "options",
    "knowledgepointid",
    "knowledgepointids",
    "taskmode",
    "status",
    "currentquestionindex",
    "totalquestions",
    "answeredquestions",
    "hintcount",
    "retrycount",
    "skipped",
}


@dataclass(frozen=True)
class ContextPolicy:
    mode: ContextMode
    version: str
    include_verified_mastery: bool
    include_self_report: bool
    include_preferences: bool
    include_conversation: bool
    include_summary: bool
    max_recent_messages: int
    max_memory_points: int
    max_context_tokens: int
    response_reserve_tokens: int
    summary_trigger_messages: int
    forbidden_fields: tuple[str, ...] = ()


class ContextPolicyRegistry:
    VERSION = "context-policy-v1"

    def __init__(self) -> None:
        version = self.VERSION
        self._policies = {
            ContextMode.PROFILE: ContextPolicy(
                ContextMode.PROFILE,
                version,
                False,
                True,
                True,
                False,
                False,
                0,
                0,
                3000,
                1000,
                0,
            ),
            ContextMode.DIAGNOSIS: ContextPolicy(
                ContextMode.DIAGNOSIS,
                version,
                True,
                False,
                False,
                False,
                False,
                0,
                80,
                5000,
                1500,
                0,
                ASSESSMENT_SECRET_FIELDS,
            ),
            ContextMode.PLANNING: ContextPolicy(
                ContextMode.PLANNING,
                version,
                True,
                True,
                True,
                False,
                False,
                0,
                120,
                7000,
                1800,
                0,
            ),
            ContextMode.TUTOR: ContextPolicy(
                ContextMode.TUTOR,
                version,
                True,
                True,
                True,
                True,
                True,
                8,
                40,
                6000,
                1800,
                8,
                ASSESSMENT_SECRET_FIELDS,
            ),
            ContextMode.REVIEW: ContextPolicy(
                ContextMode.REVIEW,
                version,
                True,
                False,
                True,
                True,
                True,
                6,
                80,
                5500,
                1600,
                6,
                ASSESSMENT_SECRET_FIELDS,
            ),
        }

    def get(self, mode: ContextMode | str) -> ContextPolicy:
        try:
            parsed = mode if isinstance(mode, ContextMode) else ContextMode(str(mode))
        except ValueError as exc:
            raise ValidationAppError(
                "unsupported context mode",
                details={"mode": str(mode)},
            ) from exc
        return self._policies[parsed]


def sanitize_payload(value: Any, forbidden_fields: tuple[str, ...]) -> Any:
    def normalize(item: Any) -> str:
        return "".join(char for char in str(item).lower() if char.isalnum())

    forbidden = {normalize(item) for item in forbidden_fields}
    if isinstance(value, dict):
        return {
            str(key): sanitize_payload(item, forbidden_fields)
            for key, item in value.items()
            if normalize(key) not in forbidden
        }
    if isinstance(value, list):
        return [sanitize_payload(item, forbidden_fields) for item in value]
    if isinstance(value, tuple):
        return [sanitize_payload(item, forbidden_fields) for item in value]
    return value


def assessment_safe_payload(value: Any) -> Any:
    """Whitelist DTO for active assessment context; answer-bearing fields cannot pass."""

    def normalize(item: Any) -> str:
        return "".join(char for char in str(item).lower() if char.isalnum())

    if isinstance(value, dict):
        return {
            str(key): assessment_safe_payload(item)
            for key, item in value.items()
            if normalize(key) in ASSESSMENT_SAFE_FIELDS
        }
    if isinstance(value, list):
        return [assessment_safe_payload(item) for item in value]
    if isinstance(value, tuple):
        return [assessment_safe_payload(item) for item in value]
    return value
