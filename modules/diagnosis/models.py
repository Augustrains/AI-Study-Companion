from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modules.common import api as common_api

STATUSES = ("未测评", "不会", "基本了解", "熟悉", "掌握")


@dataclass
class QuestionOption:
    """题目中的一个可选答案。"""

    id: str
    text: str


@dataclass
class Question(common_api.models.Identified):
    """诊断题目领域模型。"""

    title: str
    tag: str
    book_id: str = ""
    chapter_id: str = ""
    section_ids: list[str] = field(default_factory=list)
    knowledge_point_ids: list[str] = field(default_factory=list)
    ability_ids: list[str] = field(default_factory=list)
    difficulty: str = ""
    options: list[QuestionOption] = field(default_factory=list)
    source: str = ""


@dataclass
class QuestionSet:
    """Questions for one diagnostic plus server-side answer keys."""

    questions: list[Question] = field(default_factory=list)
    correct_answers: dict[str, str] = field(default_factory=dict)
    selected_skill_ids: list[str] = field(default_factory=list)


@dataclass
class KnowledgePointResult:
    """一个知识点的答题统计和诊断状态。"""

    knowledge_point_id: str
    ai_status: str
    correct: int
    total: int
    source: str = "formal_assessment"
    calibrated_status: str | None = None


@dataclass
class DiagnosisResult(common_api.models.UserOwned, common_api.models.Timestamped):
    """一次诊断完成后的最终结果。"""

    diagnosis_id: str
    user_id: str
    book_id: str
    learning_goal: str
    results: list[KnowledgePointResult]
    answer_records: list[dict[str, Any]]


@dataclass
class DiagnosticSession(
    common_api.models.Identified,
    common_api.models.UserOwned,
    common_api.models.Timestamped,
):
    """State for one complete diagnostic run, from questions to review."""

    book_id: str
    learning_goal: str
    questions: list[dict[str, Any]] = field(default_factory=list)
    correct_answers: dict[str, str] = field(default_factory=dict)
    # 当前会话中已经提交的答案；目前暂存在内存，后续需要持久化保存。
    answers: dict[str, str] = field(default_factory=dict)
    status: str = "started"
    result: dict[str, Any] | None = None
