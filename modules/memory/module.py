from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .models import MASTERY_LEVELS, EvidenceSummary, KnowledgePointMemory, LearnerMemory
from .repository import JsonMemoryRepository
from .rules import validate_knowledge_point_memory

if TYPE_CHECKING:
    from modules.diagnosis.models import DiagnosisResult


class MemoryModule:
    """Owns one durable LearnerMemory aggregate per user and domain."""

    def __init__(self, repository: JsonMemoryRepository) -> None:
        self.repository = repository

    @staticmethod
    def _domain(value: str) -> str:
        return {"machine_learning": "ml-001", "deep_learning": "dl-001"}.get(str(value), str(value))

    def get_learner_memory(self, user_id: str, learning_domain: str) -> LearnerMemory:
        domain = self._domain(learning_domain)
        return self.repository.get(user_id, domain) or LearnerMemory(user_id=user_id, learning_domain=domain)

    def _save(self, memory: LearnerMemory) -> LearnerMemory:
        memory.updated_at = self.repository.now()
        memory.update_count += 1
        return self.repository.upsert(memory)

    def sync_learner_profile(self, profile: Any) -> LearnerMemory:
        """把学习画像同步进记忆，但**不覆盖掌握度**。

        改动原因（这里原来是掌握度的第二条写入通道，而且是破坏性的）：

        1. 原实现第一步就是
           `memory.knowledge_points = [item for item in ... if id in known]`
           ——保存一次画像，所有没勾选的知识点记忆**直接被删掉**，
           包括诊断辛苦测出来的那些。
        2. 对勾选的知识点，原实现写 `mastery_level=掌握 / score=1.0 /
           confidence=1.0 / memory_status=稳定保持 / stability=60天`，
           也就是「用户说他会」等价于「满分且已稳定保持」，直接盖掉诊断结论。

        现在的规则，对应我们定下的语义：
          - 画像是**学习前的自述**，只在某个知识点还没有任何记忆时，
            作为冷启动先验落一条「未验证」的低置信记录；
          - 一旦某个知识点已经有记录（诊断产生的），自述**只作参考、不动它**；
          - 困惑和偏好属于画像自己的字段，照常同步。

        掌握度的唯一权威来源是 `ingest_diagnosis`（诊断 + 用户校准）。
        """

        memory = self.get_learner_memory(profile.user_id, profile.learning_domain)
        known = {str(item) for item in profile.known_knowledge_point_ids if item}
        now = self.repository.now()
        existing = {item.knowledge_point_id: item for item in memory.knowledge_points}
        description = str(getattr(profile, "known_knowledge_point_note", "") or "")

        for key in sorted(known):
            if key in existing:
                # 已有记忆一律保留：诊断证据优先于自述，自述不覆盖已测过的结论。
                continue
            point = KnowledgePointMemory(
                knowledge_point_id=key,
                name="",
                description=description,
                # 自述「我会」= 冷启动先验，不是结论：给最低的正向等级、
                # 低置信、未验证状态，让诊断少花一两道题在这里，但仍然会测。
                mastery_level=MASTERY_LEVELS[1],
                mastery_score=0.5,
                confidence=0.3,
                memory_status="未验证",
                memory_stability_days=0.0,
                evidence_summary=EvidenceSummary(),
                next_review_at=None,
                updated_at=now,
                update_count=1,
                source="learner_profile",
            )
            validate_knowledge_point_memory(point)
            memory.knowledge_points.append(point)

        memory.current_confusions = str(profile.current_confusions)
        memory.preferences = profile.preferences.to_dict() if hasattr(profile.preferences, "to_dict") else dict(profile.preferences.__dict__)
        return self._save(memory)

    def ingest_diagnosis(self, diagnosis: DiagnosisResult) -> LearnerMemory:
        from modules.diagnosis.models import STATUSES

        memory = self.get_learner_memory(diagnosis.user_id, diagnosis.book_id)
        total = diagnosis.answer_result.total_questions
        correct = diagnosis.answer_result.correct_questions
        memory.diagnosis_summary = {
            "diagnostic_id": diagnosis.diagnosis_id,
            "accuracy": round(correct / total * 100) if total else 0,
            "correct_count": correct,
            "total_count": total,
            "level": max((result.ai_status for result in diagnosis.results), key=lambda status: STATUSES.index(status), default=STATUSES[0]),
        }
        now = self.repository.now()
        points = {item.knowledge_point_id: item for item in memory.knowledge_points}
        for result in diagnosis.results:
            status = result.calibrated_status or result.ai_status
            previous = points.get(result.knowledge_point_id)
            points[result.knowledge_point_id] = KnowledgePointMemory(
                knowledge_point_id=result.knowledge_point_id,
                name=previous.name if previous else "",
                description=previous.description if previous else "",
                mastery_level=status,
                mastery_score=float(getattr(result, "mastery_score", 0.0)),
                confidence=float(getattr(result, "confidence", result.correct / result.total if result.total else 0.0)),
                memory_status=getattr(result, "memory_status", "未验证"),
                memory_stability_days=float(getattr(result, "memory_stability_days", 0.0)),
                evidence_summary=EvidenceSummary.from_rule_payload(getattr(result, "evidence_summary", {})),
                next_review_at=getattr(result, "next_review_at", None),
                updated_at=now,
                update_count=(previous.update_count + 1) if previous else 1,
                source=f"diagnostic:{diagnosis.diagnosis_id}",
            )
        memory.knowledge_points = list(points.values())
        return self._save(memory)

    #完成任务更新记忆
    def ingest_task_completion(self, *, user_id: str, learning_domain: str, task_id: str, knowledge_point_ids: list[str], source: str | None = None) -> LearnerMemory:
        from modules.diagnosis.models import STATUSES

        #读取用户已有的 LearnerMemory
        memory = self.get_learner_memory(user_id, learning_domain)
        #找到任务关联知识点
        points = {item.knowledge_point_id: item for item in memory.knowledge_points}
        now = self.repository.now()
        #将知识点掌握阶段提升一级，更新updated_at、update_count字段
        for key in dict.fromkeys(str(item) for item in knowledge_point_ids if item and str(item) != "unknown"):
            previous = points.get(key)
            previous_status = previous.mastery_level if previous else STATUSES[0]
            index = STATUSES.index(previous_status) if previous_status in STATUSES else 0
            points[key] = KnowledgePointMemory(
                knowledge_point_id=key,
                name=previous.name if previous else "",
                description=previous.description if previous else "",
                mastery_level=STATUSES[min(index + 1, len(STATUSES) - 1)],
                mastery_score=previous.mastery_score if previous else 0.0,
                confidence=max(previous.confidence if previous else 0.0, 0.5),
                memory_status=previous.memory_status if previous else "未验证",
                memory_stability_days=previous.memory_stability_days if previous else 0.0,
                evidence_summary=previous.evidence_summary if previous else EvidenceSummary(),
                next_review_at=previous.next_review_at if previous else None,
                updated_at=now,
                update_count=(previous.update_count + 1) if previous else 1,
                source=source or f"task:{task_id}",
            )
        memory.knowledge_points = list(points.values())
        return self._save(memory)

    def mastered_knowledge_point_ids(self, user_id: str, learning_domain: str) -> set[str]:
        mastered = {MASTERY_LEVELS[-1]}
        memory = self.get_learner_memory(user_id, learning_domain)
        return {item.knowledge_point_id for item in memory.knowledge_points if item.mastery_level in mastered}

    def knowledge_point_mastery(self, user_id: str, learning_domain: str) -> dict[str, str]:
        memory = self.get_learner_memory(user_id, learning_domain)
        return {item.knowledge_point_id: item.mastery_level for item in memory.knowledge_points}

    def list_for_user(self, user_id: str, learning_domain: str | None = None) -> list[LearnerMemory]:
        return self.repository.list_for_user(user_id, self._domain(learning_domain) if learning_domain else None)
