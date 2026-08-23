"""学习计划领域模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from modules.common import api as common_api

# 来源规则：diagnostic -> concept_review/practice/retest；
# material -> reading/concept_review；material_qa -> qa_review/concept_review；
# memory 只影响优先级和复测判断，不单独创建任务。

#任务状态，目前只用到进行+等待+已完成
LEARNING_TASK_STATUSES = [
    "todo",
    "in_progress",
    "completed",
    "review_due",
    "skipped",
    "rescheduled",
]

#表示用户接下来要做什么
#
LEARNING_TASK_TYPES = [
    "reading",
    "concept_review",
    "practice",
    "retest",
    "project",
    "qa_review",
]

LEARNING_TASK_SOURCES = ["diagnostic", "material", "material_qa", "memory"]
LEARNING_TASK_TYPES_BY_SOURCE = {
    "diagnostic": ["concept_review", "practice", "retest"],
    "material": ["reading", "concept_review"],
    "material_qa": ["qa_review", "concept_review"],
    "memory": [],
}

LEARNING_TASK_TYPE_LABELS = {
    "reading": "教材阅读",
    "concept_review": "概念复习",
    "practice": "专项练习",
    "retest": "薄弱点复测",
    "project": "项目实践",
    "qa_review": "资料问答复习",
}


@dataclass
class LearningTask:
    """一个可执行的学习任务 """

    POSSIBLE_STATUSES: ClassVar[list[str]] = LEARNING_TASK_STATUSES
    POSSIBLE_TYPES: ClassVar[list[str]] = LEARNING_TASK_TYPES

    id: str
    title: str    #标题
    type: str
    source: str
    minutes: int
    status: str = "todo"
    reason: str = ""       #原因
    description: str = ""  #任务具体描述
    learning_goal: str = ""
    expected_completion_date: str = ""
    knowledge_point_ids: list[str] = field(default_factory=list)
    ability_id: str = ""
    chapter_ids: list[str] = field(default_factory=list)
    question_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("learning task id is required")
        if self.minutes < 0:
            raise ValueError("learning task minutes cannot be negative")
        if self.status not in LEARNING_TASK_STATUSES:
            raise ValueError(f"invalid learning task status: {self.status}")
        if self.type not in LEARNING_TASK_TYPES:
            raise ValueError(f"invalid learning task type: {self.type}")
        if self.source not in LEARNING_TASK_SOURCES:
            raise ValueError(f"invalid learning task source: {self.source}")
        if self.type not in LEARNING_TASK_TYPES_BY_SOURCE[self.source]:
            raise ValueError(f"task type {self.type} is not supported by source {self.source}")

    def complete(self) -> None:
        """将任务标记为已完成。"""
        self.status = "completed"

    def to_dict(self) -> dict[str, Any]:
        """转换为本地存储和 agent 使用的 snake_case 字典。"""
        return common_api.serialization.to_data(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LearningTask":
        """从持久化任务恢复领域对象。"""
        return common_api.serialization.from_data(cls, payload)
