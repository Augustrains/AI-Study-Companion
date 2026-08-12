from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modules.common import api as common_api


@dataclass
class LongTermMemory(
    common_api.models.Identified,
    common_api.models.UserOwned,
    common_api.models.Timestamped,
):
    """A durable, derived memory used by future learning workflows."""

    learning_domain: str
    memory_type: str
    key: str
    value: Any
    confidence: float
    source: str
    def to_dict(self) -> dict[str, Any]:
        return common_api.serialization.to_data(self)
