"""Learner-profile field normalization and validation rules."""

from __future__ import annotations

import re
from typing import Any

from modules.common import api as common_api
from modules.common.errors import ValidationAppError


PROFILE_SCHEMA = {
    "user_id": common_api.schema_validator.FieldSpec(field_type=str, required=True, nullable=False, min_length=1),
    "learning_domain": common_api.schema_validator.FieldSpec(field_type=str, required=True, nullable=False, min_length=1),
    "background": common_api.schema_validator.FieldSpec(field_type=str, required=True, nullable=False, min_length=1),
    "self_assessed_level": common_api.schema_validator.FieldSpec(field_type=str, choices={"unknown", "none", "basic", "practice", "independent"}, default="unknown"),
    "known_knowledge_point_ids": common_api.schema_validator.FieldSpec(field_type=list, item_type=str, default=list),
    "known_knowledge_point_note": common_api.schema_validator.FieldSpec(field_type=str, default=""),
    "unknown_knowledge_point_ids": common_api.schema_validator.FieldSpec(field_type=list, item_type=str, default=list),
    "current_confusions": common_api.schema_validator.FieldSpec(field_type=str, default=""),
    "additional_requirements": common_api.schema_validator.FieldSpec(field_type=str, default=""),
}

PREFERENCE_SCHEMA = {
    "activity_types": common_api.schema_validator.FieldSpec(field_type=list, item_type=str, default=lambda: ["reading", "quiz"]),
    "content_style": common_api.schema_validator.FieldSpec(field_type=str, choices={"balanced", "concise", "detailed", "example_first"}, default="balanced"),
    "difficulty": common_api.schema_validator.FieldSpec(field_type=str, choices={"adaptive", "easy", "challenging"}, default="adaptive"),
    "session_duration_minutes": common_api.schema_validator.FieldSpec(field_type=int, choices={15, 30, 45, 60}, default=30),
    "learning_frequency": common_api.schema_validator.FieldSpec(field_type=str, choices={"flexible", "daily", "frequent", "occasional"}, default="flexible"),
}


def parse_profile_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValidationAppError("profile payload must be a JSON object", details={"field": "profile"})
    normalized = common_api.field_parser.parse_fields(payload, {
        "user_id": common_api.field_parser.text_value(),
        "learning_domain": common_api.field_parser.text_value(),
        "background": common_api.field_parser.text_value(),
        "self_assessed_level": common_api.field_parser.text_value("unknown"),
        "known_knowledge_point_ids": common_api.field_parser.unique_strings([]),
        "known_knowledge_point_note": common_api.field_parser.text_value(),
        "unknown_knowledge_point_ids": common_api.field_parser.unique_strings([]),
        "current_confusions": common_api.field_parser.text_value(),
        "additional_requirements": common_api.field_parser.text_value(),
    })
    raw_preferences = payload.get("preferences") or {}
    if not isinstance(raw_preferences, dict):
        raise ValidationAppError("preferences must be a JSON object", details={"field": "preferences"})
    preferences = common_api.field_parser.parse_fields(raw_preferences, {
        "activity_types": common_api.field_parser.unique_strings(),
        "content_style": common_api.field_parser.text_value("balanced"),
        "difficulty": common_api.field_parser.text_value("adaptive"),
        "session_duration_minutes": common_api.field_parser.integer_value(30),
        "learning_frequency": common_api.field_parser.text_value("flexible"),
    })
    values = common_api.schema_validator.validate_fields(normalized, PROFILE_SCHEMA)
    values["preferences"] = common_api.schema_validator.validate_fields(preferences, PREFERENCE_SCHEMA)
    note_knowledge_points = [item.strip() for item in re.split(r"[,，、;；]", values["known_knowledge_point_note"]) if item.strip()]
    values["known_knowledge_point_ids"] = list(dict.fromkeys([*values["known_knowledge_point_ids"], *note_knowledge_points]))
    values["known_knowledge_point_note"] = ", ".join(note_knowledge_points)
    return values


def normalize_profile(payload: dict[str, Any], all_knowledge_point_ids: list[str] | None = None):
    """Validate and normalize an incoming learner profile payload."""
    from .models import LearnerProfile

    values = parse_profile_payload(payload)
    if all_knowledge_point_ids is not None:
        canonical = list(dict.fromkeys(str(item) for item in all_knowledge_point_ids if item))
        known = set(values["known_knowledge_point_ids"])
        values["known_knowledge_point_ids"] = [item for item in canonical if item in known]
        values["unknown_knowledge_point_ids"] = [item for item in canonical if item not in known]
    return LearnerProfile.from_dict(values)


def apply_profile_corrections(draft: dict[str, Any], corrections: dict[str, Any], all_knowledge_point_ids: list[str] | None = None):
    """Merge user corrections and run the same canonical field pipeline."""
    if not isinstance(corrections, dict):
        raise ValidationAppError("corrections must be a JSON object", details={"field": "corrections"})
    merged = dict(draft)
    merged.update(corrections)
    if "preferences" in corrections:
        original = draft.get("preferences") or {}
        corrected = corrections.get("preferences") or {}
        if not isinstance(corrected, dict):
            raise ValidationAppError("preferences must be a JSON object", details={"field": "preferences"})
        merged["preferences"] = {**original, **corrected}
    return normalize_profile(merged, all_knowledge_point_ids)
