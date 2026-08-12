"""记忆领域自身的字段规则。"""

from __future__ import annotations

from typing import Any

from modules.common import api as common_api


MEMORY_SCHEMA = {
    "id": common_api.schema_validator.FieldSpec(str, required=True, nullable=False, min_length=1),
    "user_id": common_api.schema_validator.FieldSpec(str, required=True, nullable=False, min_length=1),
    "learning_domain": common_api.schema_validator.FieldSpec(str, required=True, nullable=False, min_length=1),
    "memory_type": common_api.schema_validator.FieldSpec(str, required=True, nullable=False, min_length=1),
    "key": common_api.schema_validator.FieldSpec(str, required=True, nullable=False, min_length=1),
    "value": common_api.schema_validator.FieldSpec(required=True, nullable=False),
    "confidence": common_api.schema_validator.FieldSpec(float, required=True, nullable=False, min_value=0.0, max_value=1.0),
    "source": common_api.schema_validator.FieldSpec(str, required=True, nullable=False, min_length=1),
    "created_at": common_api.schema_validator.FieldSpec(str, required=True, nullable=False, min_length=1),
    "updated_at": common_api.schema_validator.FieldSpec(str, required=True, nullable=False, min_length=1),
}


def validate_memory(memory: Any) -> dict[str, Any]:
    """使用 common 校验器校验记忆记录的结构和领域约束。"""
    payload = memory.to_dict() if hasattr(memory, "to_dict") else memory
    return common_api.schema_validator.validate_fields(payload, MEMORY_SCHEMA)
