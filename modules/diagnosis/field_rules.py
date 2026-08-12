"""诊断模块字段规则。

本模块只声明诊断业务自己的字段约束，具体标准化和校验能力由 common 提供。
"""

from __future__ import annotations

from typing import Any

from modules.common import api as common_api
from modules.common.errors import ValidationAppError


def _text_fields(values: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    """调用 common 标准化器，统一清理字段两端空格。"""
    return common_api.field_parser.parse_fields(
        values,
        {name: common_api.field_parser.text_value() for name in names},
    )


def parse_start_fields(user_id: str, book_id: str, learning_goal: str) -> dict[str, Any]:
    """标准化并校验诊断启动字段。"""
    normalized = _text_fields(
        {"user_id": user_id, "book_id": book_id, "learning_goal": learning_goal},
        ("user_id", "book_id", "learning_goal"),
    )
    return common_api.schema_validator.validate_fields(
        normalized,
        {
            "user_id": common_api.schema_validator.FieldSpec(field_type=str, required=True, nullable=False, min_length=1),
            "book_id": common_api.schema_validator.FieldSpec(field_type=str, required=True, nullable=False, min_length=1),
            "learning_goal": common_api.schema_validator.FieldSpec(field_type=str, nullable=False, max_length=200),
        },
    )


def parse_answer_fields(diagnosis_id: str, question_id: str, answer: str) -> dict[str, Any]:
    """标准化并校验诊断答案字段。"""
    normalized = _text_fields(
        {"diagnosis_id": diagnosis_id, "question_id": question_id, "answer": answer},
        ("diagnosis_id", "question_id", "answer"),
    )
    return common_api.schema_validator.validate_fields(
        normalized,
        {
            "diagnosis_id": common_api.schema_validator.FieldSpec(field_type=str, required=True, nullable=False, min_length=1),
            "question_id": common_api.schema_validator.FieldSpec(field_type=str, required=True, nullable=False, min_length=1),
            "answer": common_api.schema_validator.FieldSpec(field_type=str, nullable=False, max_length=200),
        },
    )


def parse_review_fields(diagnosis_id: str, calibration: str, reason: str) -> dict[str, Any]:
    """标准化并校验诊断校准字段。"""
    normalized = _text_fields(
        {"diagnosis_id": diagnosis_id, "calibration": calibration, "reason": reason},
        ("diagnosis_id", "calibration", "reason"),
    )
    return common_api.schema_validator.validate_fields(
        normalized,
        {
            "diagnosis_id": common_api.schema_validator.FieldSpec(field_type=str, required=True, nullable=False, min_length=1),
            "calibration": common_api.schema_validator.FieldSpec(field_type=str, choices={"lower", "same", "higher"}, default="same"),
            "reason": common_api.schema_validator.FieldSpec(field_type=str, nullable=False, max_length=500),
        },
    )


# Question-bank validation rules. These belong to the diagnosis module because
# they describe the input contract of diagnostic questions.
OPTION_SCHEMA = {
    "id": common_api.schema_validator.FieldSpec(
        field_type=str, required=True, nullable=False, min_length=1,
    ),
    "text": common_api.schema_validator.FieldSpec(
        field_type=str, required=True, nullable=False,
    ),
}

QUESTION_SCHEMA = {
    "id": common_api.schema_validator.FieldSpec(
        field_type=str, required=True, nullable=False, min_length=1,
    ),
    "title": common_api.schema_validator.FieldSpec(
        field_type=str, required=True, nullable=False, min_length=1,
    ),
    "tag": common_api.schema_validator.FieldSpec(
        field_type=str, required=True, nullable=False, min_length=1,
    ),
    "options": common_api.schema_validator.FieldSpec(
        field_type=list, required=True, nullable=False, item_type=dict,
    ),
    "correct_option_id": common_api.schema_validator.FieldSpec(
        field_type=str, nullable=False, min_length=1,
    ),
    "answer": common_api.schema_validator.FieldSpec(
        field_type=str, nullable=False,
    ),
    "source": common_api.schema_validator.FieldSpec(
        field_type=str, nullable=False,
    ),
}

QUESTION_BANK_SCHEMA = {
    "questions": common_api.schema_validator.FieldSpec(
        field_type=list, required=True, nullable=False, item_type=dict,
    ),
}


def validate_question_bank(payload: object) -> list[dict[str, Any]]:
    """Validate and normalize a raw question-bank payload."""
    bank = common_api.schema_validator.validate_fields(
        payload,
        QUESTION_BANK_SCHEMA,
        allow_unknown=True,
    )
    return [validate_question(item) for item in bank["questions"]]


def validate_question(item: dict[str, Any]) -> dict[str, Any]:
    """Validate one question, including option/answer relationships."""
    normalized = dict(item)
    normalized.setdefault("title", normalized.get("question", ""))
    normalized.setdefault("tag", normalized.get("knowledge_point_id", ""))
    question = common_api.schema_validator.validate_fields(
        normalized,
        QUESTION_SCHEMA,
        allow_unknown=True,
    )

    options = [
        common_api.schema_validator.validate_fields(
            option,
            OPTION_SCHEMA,
            allow_unknown=True,
        )
        for option in question["options"]
    ]
    option_ids = [option["id"] for option in options]
    if len(option_ids) != len(set(option_ids)):
        raise ValidationAppError(
            "question options must have unique ids",
            details={"question_id": question["id"]},
        )

    correct_option_id = question.get("correct_option_id", "")
    if not correct_option_id:
        answer = question.get("answer", "")
        correct_option_id = next(
            (option["id"] for option in options if option["text"] == answer),
            "",
        )
    if correct_option_id not in option_ids:
        raise ValidationAppError(
            "correct_option_id must match one of the option ids",
            details={"resource": "question_bank", "question_id": question["id"]},
        )

    return {**question, "options": options, "correct_option_id": correct_option_id}
