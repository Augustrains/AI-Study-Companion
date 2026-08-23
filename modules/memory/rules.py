from __future__ import annotations

from typing import Any

from modules.common import api as common_api

from .models import ALL_MASTERY_LEVELS, MEMORY_STATUSES

"""
定义并校验知识点记忆数据的格式和取值范围
"""
KNOWLEDGE_POINT_MEMORY_SCHEMA = {
    "knowledge_point_id": common_api.schema_validator.FieldSpec(str, required=True, nullable=False, min_length=1),
    "name": common_api.schema_validator.FieldSpec(str, required=True, nullable=False),
    "description": common_api.schema_validator.FieldSpec(str, required=True, nullable=False),
    "mastery_level": common_api.schema_validator.FieldSpec(str, required=True, nullable=False, choices=set(ALL_MASTERY_LEVELS)),
    "mastery_score": common_api.schema_validator.FieldSpec(float, required=True, nullable=False, min_value=0.0, max_value=1.0),
    "confidence": common_api.schema_validator.FieldSpec(float, required=True, nullable=False, min_value=0.0, max_value=1.0),
    "memory_status": common_api.schema_validator.FieldSpec(str, required=True, nullable=False, choices=set(MEMORY_STATUSES)),
    "memory_stability_days": common_api.schema_validator.FieldSpec(float, required=True, nullable=False, min_value=0.0),
    "evidence_summary": common_api.schema_validator.FieldSpec(dict, required=True, nullable=False),
    "next_review_at": common_api.schema_validator.FieldSpec((str, type(None)), required=True, nullable=True),
    "updated_at": common_api.schema_validator.FieldSpec(str, required=True, nullable=False, min_length=1),
    "update_count": common_api.schema_validator.FieldSpec(int, required=True, nullable=False, min_value=1),
    "source": common_api.schema_validator.FieldSpec(str, required=True, nullable=False, min_length=1),
}


def validate_knowledge_point_memory(memory: Any) -> dict[str, Any]:
    payload = memory.to_dict() if hasattr(memory, "to_dict") else memory
    return common_api.schema_validator.validate_fields(payload, KNOWLEDGE_POINT_MEMORY_SCHEMA)
