"""今日学习模块的请求字段规则。"""

from __future__ import annotations

from typing import Any

from modules.common import api as common_api


TODAY_LEARNING_QUERY_SCHEMA = {
    "user_id": common_api.schema_validator.FieldSpec(str, required=True, nullable=False, min_length=1),
    "book_id": common_api.schema_validator.FieldSpec(str, required=True, nullable=False, min_length=1),
}


def validate_query(user_id: str, book_id: str) -> dict[str, Any]:
    return common_api.schema_validator.validate_fields(
        {"user_id": user_id.strip(), "book_id": book_id.strip()},
        TODAY_LEARNING_QUERY_SCHEMA,
    )

