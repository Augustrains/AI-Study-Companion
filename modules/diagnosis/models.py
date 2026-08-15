"""诊断模块的数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict

from modules.common import api as common_api


STATUSES = ("未测评", "不会", "了解", "熟悉", "掌握")
TASK_MODES = (
    "diagnostic",
    "guided_practice",
    "independent",
    "retrieval",
    "remediation",
    "challenge",
)


@dataclass(frozen=True)
class QuestionPlanningInput:
    """交给 LLM 的候选知识点和已有学习状态。"""

    learning_goal: str
    knowledge_point_mastery: dict[str, str]
    knowledge_point_memory: dict[str, dict[str, Any]]
    available_question_counts: dict[str, int]
    knowledge_point_catalog: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgePointQuestionPlan:
    """LLM 为一个知识点返回的出题决策。"""

    knowledge_point_id: str
    question_count: int
    task_mode: str


@dataclass
class Question(common_api.models.Identified):
    """根据知识点计划取得的一道诊断题。"""

    title: str
    tag: str
    book_id: str = ""
    chapter_id: str = ""
    section_ids: list[str] = field(default_factory=list)
    knowledge_point_ids: list[str] = field(default_factory=list)
    task_mode: str = "diagnostic"
    options: list[dict[str, str]] = field(default_factory=list)
    source: str = ""


@dataclass(frozen=True)
class AnswerRecord:
    """用户对一道题的作答事实。"""

    question: Question
    submitted_answer: str
    correct_answer: str
    is_correct: bool
    skipped: bool
    hint_count: int = 0
    retry_count: int = 0
    is_independent: bool = True
    is_delayed_retrieval: bool = False
    occurred_at: str = ""


@dataclass(frozen=True)
class AnswerResult:
    """一次诊断的逐题记录和整体答题统计。"""

    answer_records: list[AnswerRecord]
    total_questions: int
    answered_questions: int
    skipped_questions: int
    correct_questions: int
    accuracy: float
    confidence: str


@dataclass
class KnowledgePointResult:
    """规则算法计算出的一个知识点诊断结果。"""

    knowledge_point_id: str
    ai_status: str
    correct: int
    total: int
    mastery_score: float = 0.0
    memory_status: str = "未验证"
    memory_stability_days: float = 0.0
    confidence: float = 0.0
    evidence_ids: list[str] = field(default_factory=list)
    evidence_summary: dict[str, Any] = field(default_factory=dict)
    reason_codes: list[str] = field(default_factory=list)
    algorithm_name: str = ""
    algorithm_version: str = ""
    next_review_at: str | None = None
    source: str = "formal_assessment"
    calibrated_status: str | None = None


@dataclass
class DiagnosisResult(common_api.models.UserOwned, common_api.models.Timestamped):
    """知识点诊断结果与用户反馈组成的最终结果。"""

    diagnosis_id: str
    user_id: str
    book_id: str
    learning_goal: str
    answer_result: AnswerResult
    results: list[KnowledgePointResult]
    calibration: str = "same"
    calibration_reason: str = ""

    @property
    def answer_records(self) -> list[AnswerRecord]:
        return self.answer_result.answer_records


class DiagnosisState(TypedDict, total=False):
    """一轮诊断在 LangGraph 节点之间传递的状态。"""

    diagnosis_id: str
    user_id: str
    book_id: str
    learning_goal: str
    knowledge_point_mastery: dict[str, str]
    knowledge_point_memory: dict[str, dict[str, Any]]
    questions: list[dict[str, Any]]
    correct_answers: dict[str, str]
    answers: dict[str, str]
    answer_metadata: dict[str, dict[str, Any]]
    draft_results: list[dict[str, Any]]
    answer_result: dict[str, Any]
    review_action: str
    calibrations: dict[str, str]
    status: str
