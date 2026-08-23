"""统一的数据类与 JSON 兼容数据之间的转换工具。"""

from __future__ import annotations

from dataclasses import MISSING, fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from types import UnionType
from typing import Any, TypeVar, Union, get_args, get_origin, get_type_hints

from .errors import SerializationAppError

T = TypeVar("T")


def to_data(value: Any) -> Any:
    """递归地将领域对象转换为 JSON 可编码的数据。

    支持数据类、枚举、日期时间、字典以及列表/元组/集合。
    该函数只负责结构转换，不负责业务字段校验。
    """
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: to_data(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Enum):
        return to_data(value.value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): to_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_data(item) for item in value]
    return value


def from_data(target_type: type[T], value: Any, *, field_name: str = "root") -> T:
    """根据类型标注将 JSON 数据转换为目标类型。

    Args:
        target_type: 目标 Python 类型，通常是一个数据类。
        value: FastAPI 请求体、JSON 文件或其他外部来源产生的数据。
        field_name: 当前字段路径，用于在异常中定位具体字段。

    Raises:
        SerializationAppError: 类型不匹配、字段缺失或出现未知字段时抛出。
    """
    try:
        return _convert(target_type, value, field_name)
    except SerializationAppError:
        raise
    except (TypeError, ValueError, KeyError) as exc:
        raise SerializationAppError(
            f"cannot deserialize {field_name} as {getattr(target_type, '__name__', target_type)}",
            details={"field": field_name, "target_type": str(target_type)},
            cause=exc,
        ) from exc


def _convert(target_type: Any, value: Any, field_name: str) -> Any:
    """递归执行具体类型转换；内部异常由 from_data 统一包装。"""
    if target_type is Any or target_type is None:
        return value
    if value is None:
        if type(None) in get_args(target_type) or target_type is type(None):
            return None
        raise TypeError("value cannot be null")
    origin, args = get_origin(target_type), get_args(target_type)
    if origin in (Union, UnionType):
        for candidate in args:
            if candidate is not type(None):
                try:
                    return _convert(candidate, value, field_name)
                except (TypeError, ValueError, SerializationAppError):
                    pass
        raise TypeError("no union member matched")
    if origin is list:
        if not isinstance(value, list):
            raise TypeError("expected a list")
        item_type = args[0] if args else Any
        return [_convert(item_type, item, f"{field_name}[{index}]") for index, item in enumerate(value)]
    if origin is dict:
        if not isinstance(value, dict):
            raise TypeError("expected an object")
        key_type, item_type = args or (Any, Any)
        return {_convert(key_type, key, field_name): _convert(item_type, item, field_name) for key, item in value.items()}
    if isinstance(target_type, type) and issubclass(target_type, Enum):
        return target_type(value)
    if target_type in (datetime, date, time):
        return target_type.fromisoformat(value)
    if is_dataclass(target_type):
        if not isinstance(value, dict):
            raise TypeError("expected an object")
        hints = get_type_hints(target_type)
        known = {item.name for item in fields(target_type)}
        unknown = sorted(set(value) - known)
        if unknown:
            raise TypeError(f"unknown fields: {', '.join(unknown)}")
        kwargs = {}
        for item in fields(target_type):
            if item.name in value:
                kwargs[item.name] = _convert(hints.get(item.name, item.type), value[item.name], f"{field_name}.{item.name}")
            elif item.default is MISSING and item.default_factory is MISSING:
                raise TypeError(f"missing field: {item.name}")
        return target_type(**kwargs)
    if target_type is bool:
        if not isinstance(value, bool):
            raise TypeError("expected a boolean")
        return value
    if target_type in (str, int, float):
        if not isinstance(value, target_type) or (target_type is int and isinstance(value, bool)):
            raise TypeError(f"expected {target_type.__name__}")
        return value
    return value
