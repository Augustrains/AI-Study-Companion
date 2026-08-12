"""学习记录字段规则，复用 common 的统一字段校验器。"""

from __future__ import annotations

from typing import Any

from modules.common import api as common_api

from .models import ACTIVITY_CATEGORIES, ACTIVITY_STATUSES, ACTIVITY_TYPES


LEARNING_ACTIVITY_SCHEMA = {
    "id": common_api.schema_validator.FieldSpec(str, required=True, nullable=False, min_length=1),
    "user_id": common_api.schema_validator.FieldSpec(str, required=True, nullable=False, min_length=1),
    "category": common_api.schema_validator.FieldSpec(
        str, required=True, nullable=False, choices=set(ACTIVITY_CATEGORIES)
    ),
    "activity_type": common_api.schema_validator.FieldSpec(
        str, required=True, nullable=False, choices=set(ACTIVITY_TYPES)
    ),
    "status": common_api.schema_validator.FieldSpec(
        str, required=True, nullable=False, choices=set(ACTIVITY_STATUSES)
    ),
    "title": common_api.schema_validator.FieldSpec(str, required=True, nullable=False, min_length=1),
    "description": common_api.schema_validator.FieldSpec(str, required=True, nullable=False),
    "occurred_at": common_api.schema_validator.FieldSpec(str, required=True, nullable=False, min_length=1),
    "created_at": common_api.schema_validator.FieldSpec(str, required=True, nullable=False, min_length=1),
    "updated_at": common_api.schema_validator.FieldSpec(str, required=True, nullable=False, min_length=1),
    "book_id": common_api.schema_validator.FieldSpec(str, required=True, nullable=False),
    "learning_goal_id": common_api.schema_validator.FieldSpec(str, required=True, nullable=False),
    "plan_id": common_api.schema_validator.FieldSpec(str, required=True, nullable=False),
    "task_id": common_api.schema_validator.FieldSpec(str, required=True, nullable=False),
    "diagnostic_id": common_api.schema_validator.FieldSpec(str, required=True, nullable=False),
    "qa_conversation_id": common_api.schema_validator.FieldSpec(str, required=True, nullable=False),
    "learner_profile_id": common_api.schema_validator.FieldSpec(str, required=True, nullable=False),
    "knowledge_point_ids": common_api.schema_validator.FieldSpec(list, required=True, nullable=False, item_type=str),
    "result": common_api.schema_validator.FieldSpec(dict, required=True, nullable=False),
    "detail": common_api.schema_validator.FieldSpec(dict, required=True, nullable=False),
    "client_request_id": common_api.schema_validator.FieldSpec(str, required=True, nullable=False),
    "source": common_api.schema_validator.FieldSpec(str, required=True, nullable=False, min_length=1),
}


def validate_learning_activity(activity: Any) -> dict[str, Any]:
    """校验一个从 JSON 读取或由领域对象转换而来的活动记录。"""

    payload = common_api.serialization.to_data(activity)
    validated = common_api.schema_validator.validate_fields(
        payload,
        LEARNING_ACTIVITY_SCHEMA,
    )
    _validate_activity_relation(validated)
    return validated


def _validate_activity_relation(payload: dict[str, Any]) -> None:
    """校验活动分类与具体类型的业务对应关系。"""

    category = payload["category"]
    activity_type = payload["activity_type"]
    expected_category = {
        "profile": {"profile_created", "profile_updated"},
        "qa": {"qa_started", "qa_asked", "qa_answered"},
        "diagnostic": {"diagnostic_started", "diagnostic_completed", "diagnostic_calibrated", "review_completed"},
        "task": {"task_completed"},
    }
    if activity_type not in expected_category[category]:
        raise common_api.errors.ValidationAppError(
            "activity_type does not match category",
            details={"category": category, "activity_type": activity_type},
        )
