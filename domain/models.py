from dataclasses import dataclass, field
from typing import Any

from .learner_profile import LearnerProfile

STATUSES = ("未测评", "不会", "基本了解", "熟悉", "掌握")


@dataclass(frozen=True)
class Question:
    id: str
    knowledge_point_id: str
    question: str
    answer: str
    options: list[str] = field(default_factory=list)
    source: str = ""


@dataclass
class KnowledgePointResult:
    knowledge_point_id: str
    ai_status: str
    correct: int
    total: int
    source: str = "formal_assessment"
    explanation: str = ""
    calibrated_status: str | None = None


@dataclass
class DiagnosisResult:
    diagnosis_id: str
    user_id: str
    book_id: str
    learning_goal: str
    results: list[KnowledgePointResult]
    answer_records: list[dict[str, Any]]


@dataclass
class LearningSession:
    id: str
    user_id: str
    book_id: str
    learning_goal: str
    learner_profile: LearnerProfile | None = None
    knowledge_states: dict[str, str] = field(default_factory=dict)
    diagnosis_history: list[dict[str, Any]] = field(default_factory=list)
    calibration_history: list[dict[str, Any]] = field(default_factory=list)

    def apply_diagnosis(self, diagnosis: DiagnosisResult) -> None:
        for result in diagnosis.results:
            self.knowledge_states[result.knowledge_point_id] = result.ai_status
        self.diagnosis_history.append(
            {
                "diagnosis_id": diagnosis.diagnosis_id,
                "results": [result.__dict__.copy() for result in diagnosis.results],
                "answer_records": diagnosis.answer_records,
            }
        )

    def calibrate(self, knowledge_point_id: str, status: str) -> None:
        if status not in STATUSES[1:]:
            raise ValueError(f"不支持的校准状态: {status}")
        previous = self.knowledge_states.get(knowledge_point_id, "未测评")
        self.knowledge_states[knowledge_point_id] = status
        self.calibration_history.append(
            {
                "knowledge_point_id": knowledge_point_id,
                "previous_status": previous,
                "calibrated_status": status,
                "source": "user_calibration",
            }
        )
