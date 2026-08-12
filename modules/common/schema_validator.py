"""通用字段校验器。

本模块负责校验字段是否符合声明的结构约束；字段去空格、默认值和格式
转换仍由 ``field_parser`` 负责。校验失败时一次性返回所有字段问题。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from .errors import ValidationAppError

UNSET = object()
CustomValidator = Callable[[Any], str | None]


@dataclass(frozen=True)
class FieldSpec:
    """一个字段的通用校验规则。"""

    field_type: type | tuple[type, ...] | None = None
    required: bool = False
    nullable: bool = True
    default: Any = UNSET
    min_value: int | float | None = None
    max_value: int | float | None = None
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    choices: set[Any] | None = None
    item_type: type | tuple[type, ...] | None = None
    validator: CustomValidator | None = None


@dataclass
class FieldIssue:
    """单个字段的校验问题。"""

    field: str
    code: str
    message: str
    value: Any = None


def validate_fields(payload: object, schema: dict[str, FieldSpec], *, allow_unknown: bool = False) -> dict[str, Any]:
    """按照字段模板校验对象，并返回校验后的字段字典。

    Args:
        payload: 待校验的字典，通常来自请求体或 JSON 文件。
        schema: 字段名到 ``FieldSpec`` 的映射。
        allow_unknown: 是否允许 schema 未声明的字段。

    Raises:
        ValidationAppError: 输入不是对象，或存在一个及以上字段问题。
    """
    if not isinstance(payload, dict):
        raise ValidationAppError("request data must be a JSON object")
    
    #收集字段错误
    issues: list[FieldIssue] = []
    result: dict[str, Any] = {}
    if not allow_unknown:
        for name in sorted(set(payload) - set(schema)):
            issues.append(FieldIssue(name, "UNKNOWN_FIELD", f"unknown field: {name}"))

    for name, spec in schema.items():
        if name not in payload:
            if spec.required:
                issues.append(FieldIssue(name, "REQUIRED", f"{name} is required"))
            elif spec.default is not UNSET:
                result[name] = spec.default() if callable(spec.default) else spec.default
            continue

        value = payload[name]
        field_issues = _validate_one(name, value, spec)
        if field_issues:
            issues.extend(field_issues)
        else:
            result[name] = value

    if issues:
        raise ValidationAppError(
            "field validation failed",
            details={"issues": [issue.__dict__ for issue in issues]},
        )
    return result


def _validate_one(name: str, value: Any, spec: FieldSpec) -> list[FieldIssue]:
    """负责校验单个字段是否符合对应的规则"""
    issues: list[FieldIssue] = []
    if value is None:
        if not spec.nullable:
            issues.append(FieldIssue(name, "NULL_NOT_ALLOWED", f"{name} cannot be null"))
        return issues

    if spec.field_type is not None and (
        not isinstance(value, spec.field_type) 
        or (spec.field_type is int and isinstance(value, bool))
    ):
        return [FieldIssue(name, "TYPE_MISMATCH", f"{name} must be { _type_name(spec.field_type) }", value)]

    if spec.choices is not None and value not in spec.choices:
        issues.append(FieldIssue(name, "INVALID_CHOICE", f"{name} must be one of {sorted(spec.choices)}", value))
    if spec.min_value is not None and value < spec.min_value:
        issues.append(FieldIssue(name, "VALUE_TOO_SMALL", f"{name} must be at least {spec.min_value}", value))
    if spec.max_value is not None and value > spec.max_value:
        issues.append(FieldIssue(name, "VALUE_TOO_LARGE", f"{name} must be at most {spec.max_value}", value))
    if spec.min_length is not None and len(value) < spec.min_length:
        issues.append(FieldIssue(name, "LENGTH_TOO_SHORT", f"{name} is too short", value))
    if spec.max_length is not None and len(value) > spec.max_length:
        issues.append(FieldIssue(name, "LENGTH_TOO_LONG", f"{name} is too long", value))
    if spec.pattern is not None and (not isinstance(value, str) or re.fullmatch(spec.pattern, value) is None):
        issues.append(FieldIssue(name, "INVALID_FORMAT", f"{name} has an invalid format", value))
    if spec.item_type is not None:
        if not isinstance(value, list):
            issues.append(FieldIssue(name, "TYPE_MISMATCH", f"{name} must be a list", value))
        elif any(not isinstance(item, spec.item_type) for item in value):
            issues.append(FieldIssue(name, "ITEM_TYPE_MISMATCH", f"items in {name} have an invalid type", value))
    if spec.validator is not None:
        message = spec.validator(value)
        if message:
            issues.append(FieldIssue(name, "CUSTOM_VALIDATION", message, value))
    return issues


def _type_name(value: type | tuple[type, ...]) -> str:
    """生成面向开发者的类型名称。"""
    types = value if isinstance(value, tuple) else (value,)
    return " or ".join(item.__name__ for item in types)
