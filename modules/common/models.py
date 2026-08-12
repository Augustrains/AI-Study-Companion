"""跨业务模块共享的数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


@dataclass(kw_only=True)
class Identified:
    """带有稳定唯一标识的数据对象。"""

    id: str


@dataclass(kw_only=True)
class UserOwned:
    """表示数据对象归属于某个用户。"""

    user_id: str


@dataclass(kw_only=True)
class Timestamped:
    """记录对象的创建时间和最后更新时间。"""

    created_at: str = ""
    updated_at: str = ""


@dataclass
class ValidationIssue:
    """描述一条数据校验问题。"""

    field: str
    code: str
    message: str
    severity: str = "error"
    details: dict[str, Any] | None = None


@dataclass
class ValidationResult:
    """表示一次数据校验的总体结果及其问题列表。"""

    valid: bool
    issues: list[ValidationIssue]


@dataclass
class Correction:
    """描述一个字段从原始值到修正值的变化。"""

    field: str
    original_value: Any
    corrected_value: Any
    reason: str = ""


@dataclass
class CorrectionResult:
    """表示一次修正操作的结果。"""

    corrected: bool
    corrections: list[Correction]
    warnings: list[str]


class ReviewAction(StrEnum):
    """工作流审核动作：通过、编辑或拒绝。"""

    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"
