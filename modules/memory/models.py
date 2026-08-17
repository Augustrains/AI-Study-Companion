from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modules.common import api as common_api


# "未测评" 是初始状态；以下四项是知识点实际的掌握阶段。
MASTERY_LEVELS = ("不会", "了解", "熟悉", "掌握")
INITIAL_MASTERY_LEVEL = "未测评"
ALL_MASTERY_LEVELS = (INITIAL_MASTERY_LEVEL, *MASTERY_LEVELS)
MEMORY_STATUSES = ("未验证", "首次验证", "延迟复测通过", "稳定保持")


@dataclass
class EvidenceSummary:
    """累计答题证据统计，供下一次掌握度增量计算使用。"""

    accepted_evidence_count: int = 0                #已采纳的有效答题证据总数
    effective_evidence_weight: float = 0.0          #有效证据总权重
    independent_correct_count: int = 0              #独立完成并答对的次数
    delayed_correct_count: int = 0                  #延迟回忆，并答对的次数
    delayed_failure_count: int = 0                  #进行延迟回忆时答错的次数
    guided_evidence_count: int = 0                  #在提示、引导或辅助下完成的答题证据数量

    @classmethod
    def from_rule_payload(cls, payload: dict[str, Any] | None) -> "EvidenceSummary":
        payload = payload or {}
        return cls(
            accepted_evidence_count=int(payload.get("acceptedEvidenceCount", 0)),
            effective_evidence_weight=float(payload.get("effectiveEvidenceWeight", 0.0)),
            independent_correct_count=int(payload.get("independentCorrectCount", 0)),
            delayed_correct_count=int(payload.get("delayedCorrectCount", 0)),
            delayed_failure_count=int(payload.get("delayedFailureCount", 0)),
            guided_evidence_count=int(payload.get("guidedEvidenceCount", 0)),
        )

    def to_rule_payload(self) -> dict[str, Any]:
        return {
            "acceptedEvidenceCount": self.accepted_evidence_count,
            "effectiveEvidenceWeight": self.effective_evidence_weight,
            "independentCorrectCount": self.independent_correct_count,
            "delayedCorrectCount": self.delayed_correct_count,
            "delayedFailureCount": self.delayed_failure_count,
            "guidedEvidenceCount": self.guided_evidence_count,
        }


@dataclass
class KnowledgePointMemory:
    """Current memory state for one knowledge point."""

    knowledge_point_id: str
    name: str = ""
    description: str = ""   #知识点描述
    mastery_level: str = INITIAL_MASTERY_LEVEL     #掌握阶段
    mastery_score: float = 0.0                     #规则算法计算出的掌握分数
    confidence: float = 0.0                        #当前诊断结果的置信度
    memory_status: str = MEMORY_STATUSES[0]         #记忆验证状态
    memory_stability_days: float = 0.0             #预计当前记忆可以稳定保持的天数
    evidence_summary: EvidenceSummary = field(default_factory=EvidenceSummary)  #历史证据统计
    next_review_at: str | None = None                               #建议下次复习或复测时间
    updated_at: str = ""                     #该知识点记忆最近一次更新时间
    update_count: int = 0                    #该知识点记忆累计更新次数
    source: str = ""                         #记忆来源
    assessed_mastery_level: str | None = None  #规则算法给出的正式掌握阶段
    user_calibrated_level: str | None = None   #用户确认/校准后的主观阶段
    evidence_ids: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    algorithm_name: str = ""
    algorithm_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return common_api.serialization.to_data(self)


@dataclass
class LearnerMemory:
    """Complete durable memory for one learner in one learning domain."""

    user_id: str
    learning_domain: str
    knowledge_points: list[KnowledgePointMemory] = field(default_factory=list)
    learning_goals: list[str] = field(default_factory=list)
    diagnosis_summary: dict[str, Any] = field(default_factory=dict)
    current_confusions: str = ""
    preferences: dict[str, Any] = field(default_factory=dict)
    self_assessed_level: str = "unknown"
    self_reported_known_knowledge_point_ids: list[str] = field(default_factory=list)
    self_reported_unknown_knowledge_point_ids: list[str] = field(default_factory=list)
    self_reported_knowledge_point_note: str = ""
    last_completed_task_id: str = ""
    last_activity_at: str = ""
    completed_task_count: int = 0
    state_version: int = 0
    updated_at: str = ""
    update_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return common_api.serialization.to_data(self)
