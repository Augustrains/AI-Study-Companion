from dataclasses import dataclass, field
from typing import Any

@dataclass
class EvidenceSummary:
    accepted_evidence_count: int = 0
    effective_evidence_weight: float = 0.0
    independent_correct_count: int = 0
    delayed_correct_count: int = 0
    delayed_failure_count: int = 0
    guided_evidence_count: int = 0

@dataclass
class KnowledgePointMemory:
    knowledge_point_id: str
    name: str = ""
    description: str = ""
    mastery_level: str = "未测评"
    mastery_score: float = 0.0
    confidence: float = 0.0
    memory_status: str = "未验证"
    memory_stability_days: float = 0.0
    evidence_summary: EvidenceSummary = field(default_factory=EvidenceSummary)
    next_review_at: str | None = None
    updated_at: str = ""
    update_count: int = 0
    source: str = ""

@dataclass
class LearnerMemory:
    user_id: str
    learning_domain: str
    knowledge_points: list[KnowledgePointMemory] = field(default_factory=list)
    learning_goals: list[str] = field(default_factory=list)
    diagnosis_summary: dict[str, Any] = field(default_factory=dict)
    current_confusions: str = ""
    preferences: dict[str, Any] = field(default_factory=dict)
    updated_at: str = ""
    update_count: int = 0
