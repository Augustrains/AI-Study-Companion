"""通用请求字段标准化工具。

本模块只负责清洗和转换原始字段，例如去除空格、填充默认值、转换整数
以及列表去重。字段类型、必填、范围、长度和枚举等约束由
``modules.common.schema_validator`` 负责。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .errors import ValidationAppError

FieldRule = Callable[[object, Mapping[str, Any]], Any]


def parse_fields(payload: object, rules: Mapping[str, FieldRule]) -> dict[str, Any]:
    """按字段标准化规则处理请求体，并返回标准化后的字段字典。"""
    if not isinstance(payload, dict):
        raise ValidationAppError("request body must be a JSON object")
    return {field: rule(payload.get(field), payload) for field, rule in rules.items()}


def text_value(default: str = "") -> FieldRule:
    """清理文本字段两端空格，并在空值时使用默认值。"""
    return lambda value, _payload: str(value or "").strip() or default


def integer_value(default: int = 0) -> FieldRule:
    """将可转换的值标准化为整数；具体范围由校验器检查。"""
    def parse(value: object, _payload: Mapping[str, Any]) -> object:
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return value

    return parse


def unique_strings(default: list[str] | None = None) -> FieldRule:
    """清理字符串列表、过滤空字符串并去除重复项。

    如果输入不是列表，则原样保留，让 schema_validator 统一报告类型错误。
    """
    def parse(value: object, _payload: Mapping[str, Any]) -> object:
        actual = default if value is None else value
        if not isinstance(actual, list):
            return actual
        values = (str(item or "").strip() for item in actual)
        return list(dict.fromkeys(item for item in values if item))

    return parse
