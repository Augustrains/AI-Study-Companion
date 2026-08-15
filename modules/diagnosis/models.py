from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict

from modules.common import api as common_api

STATUSES = ("未测评", "不会", "了解", "熟悉", "掌握")


class DiagnosisState(TypedDict, total=False):
    """Transient state shared by diagnosis workflow nodes."""

    workflow_run_id: str
    diagnosis_id: str
    diagnostic_session_id: str
    user_id: str
    book_id: str
    learning_goal: str
    # TODO(task-context): 由学习任务模块提供题目任务上下文。
    task_context: dict[str, Any]
    knowledge_point_mastery: dict[str, str]
    knowledge_point_memory: dict[str, dict[str, Any]]
    question_plan: list[dict[str, Any]]
    questions: list[dict[str, Any]]
    correct_answers: dict[str, str]
    answers: dict[str, str]
    draft_results: list[dict[str, Any]]
    answer_records: list[dict[str, Any]]
    analysis_input: dict[str, Any]
    review_action: str
    calibrations: dict[str, str]
    status: str


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
    task_mode: str = "diagnostic"
    # TODO(task-context): 题目实例后续需要携带 task_mode、is_delayed_retrieval、
    # scheduled_interval_days 等学习任务上下文，不能只依赖题库中的静态题目数据。
    task_context: dict[str, Any] = field(default_factory=dict)
    options: list[QuestionOption] = field(default_factory=list)
    source: str = ""


@dataclass
class QuestionSet:
    """Questions for one diagnostic plus server-side answer keys."""

    questions: list[Question] = field(default_factory=list)
    correct_answers: dict[str, str] = field(default_factory=dict)
    selected_knowledge_point_ids: list[str] = field(default_factory=list)


@dataclass
class KnowledgePointResult:
    """一个知识点的答题统计和诊断状态。"""

    knowledge_point_id: str
    ai_status: str          #掌握阶段
    correct: int            #掌握分数
    total: int
    mastery_score: float = 0.0
    memory_status: str = "未验证"     #记忆验证状态
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
    """一次诊断完成后的最终结果。"""

    diagnosis_id: str
    user_id: str
    book_id: str
    learning_goal: str
    results: list[KnowledgePointResult]   #每个知识点的诊断结果
    answer_records: list[dict[str, Any]]  #每道题的答题记录


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
    answer_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    calibration: str = ""
    calibration_reason: str = ""
    status: str = "started"
    result: dict[str, Any] | None = None
