from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from modules.common import api as common_api


class MemoryEventType(StrEnum):
    PROFILE_DECLARED = "profile_declared"
    PREFERENCE_CONFIRMED = "preference_confirmed"
    DIAGNOSIS_CONFIRMED = "diagnosis_confirmed"
    DELAYED_REVIEW_GRADED = "delayed_review_graded"
    TASK_COMPLETED = "task_completed"
    LEGACY_SNAPSHOT = "legacy_snapshot"


@dataclass(frozen=True)
class MemoryEvent:
    """Immutable, idempotent evidence submitted to the memory projector."""

    event_id: str
    user_id: str
    learning_domain: str
    event_type: str
    source_type: str
    occurred_at: str
    payload: dict[str, Any] = field(default_factory=dict)
    knowledge_point_id: str | None = None
    algorithm_version: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return common_api.serialization.to_data(self)

    def payload_hash(self) -> str:
        semantic_payload = {
            "event_id": self.event_id,
            "user_id": self.user_id,
            "learning_domain": self.learning_domain,
            "event_type": self.event_type,
            "source_type": self.source_type,
            "knowledge_point_id": self.knowledge_point_id,
            "algorithm_version": self.algorithm_version,
            "payload": self.payload,
        }
        raw = json.dumps(
            semantic_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()
