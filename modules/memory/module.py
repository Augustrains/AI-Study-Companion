from __future__ import annotations

from threading import Lock, RLock
from typing import TYPE_CHECKING, Any

from modules.common import api as common_api

from .events import MemoryEvent, MemoryEventType
from .models import MASTERY_LEVELS, EvidenceSummary, KnowledgePointMemory, LearnerMemory
from .repository import MemoryRepository
from .rules import validate_knowledge_point_memory

if TYPE_CHECKING:
    from modules.diagnosis.models import DiagnosisResult


class MemoryModule:
    """Owns one durable LearnerMemory aggregate per user and domain."""

    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository
        self._aggregate_locks: dict[tuple[str, str], RLock] = {}
        self._aggregate_locks_guard = Lock()

    def _lock_for(self, user_id: str, learning_domain: str) -> RLock:
        key = (str(user_id), self._domain(learning_domain))
        with self._aggregate_locks_guard:
            return self._aggregate_locks.setdefault(key, RLock())

    @staticmethod
    def _domain(value: str) -> str:
        return {
            "ml": "ml-001",
            "ml-001": "ml-001",
            "machine_learning": "ml-001",
            "dl": "dl-001",
            "dl-001": "dl-001",
            "deep_learning": "dl-001",
        }.get(str(value), str(value))

    def get_learner_memory(self, user_id: str, learning_domain: str) -> LearnerMemory:
        domain = self._domain(learning_domain)
        return self.repository.get(user_id, domain) or LearnerMemory(user_id=user_id, learning_domain=domain)

    def _save(self, memory: LearnerMemory) -> LearnerMemory:
        memory.updated_at = self.repository.now()
        memory.update_count += 1
        return self.repository.upsert(memory)

    def _apply_event(self, memory: LearnerMemory, event: MemoryEvent) -> LearnerMemory:
        expected_version = memory.state_version
        memory.updated_at = self.repository.now()
        memory.update_count += 1
        apply_event = getattr(self.repository, "apply_event", None)
        if callable(apply_event):
            return apply_event(memory, event, expected_version=expected_version)
        return self.repository.upsert(memory)

    def sync_learner_profile(self, profile: Any) -> LearnerMemory:
        with self._lock_for(profile.user_id, profile.learning_domain):
            return self._sync_learner_profile(profile)

    def _sync_learner_profile(self, profile: Any) -> LearnerMemory:
        memory = self.get_learner_memory(profile.user_id, profile.learning_domain)
        known = {str(item) for item in profile.known_knowledge_point_ids if item}
        unknown = {
            str(item)
            for item in getattr(profile, "unknown_knowledge_point_ids", [])
            if item
        }
        memory.self_assessed_level = str(
            getattr(profile, "self_assessed_level", "unknown") or "unknown"
        )
        memory.self_reported_known_knowledge_point_ids = sorted(known)
        memory.self_reported_unknown_knowledge_point_ids = sorted(unknown)
        memory.self_reported_knowledge_point_note = str(
            getattr(profile, "known_knowledge_point_note", "") or ""
        )
        memory.current_confusions = str(profile.current_confusions)
        memory.preferences = profile.preferences.to_dict() if hasattr(profile.preferences, "to_dict") else dict(profile.preferences.__dict__)
        occurred_at = str(getattr(profile, "updated_at", "") or self.repository.now())
        return self._apply_event(
            memory,
            MemoryEvent(
                event_id=f"profile:{memory.user_id}:{memory.learning_domain}:{occurred_at}",
                user_id=memory.user_id,
                learning_domain=memory.learning_domain,
                event_type=MemoryEventType.PROFILE_DECLARED,
                source_type="self_report",
                occurred_at=occurred_at,
                payload={
                    "self_assessed_level": memory.self_assessed_level,
                    "known_knowledge_point_ids": memory.self_reported_known_knowledge_point_ids,
                    "unknown_knowledge_point_ids": memory.self_reported_unknown_knowledge_point_ids,
                    "known_knowledge_point_note": memory.self_reported_knowledge_point_note,
                    "current_confusions": memory.current_confusions,
                    "preferences": memory.preferences,
                },
            ),
        )

    def ingest_diagnosis(self, diagnosis: DiagnosisResult) -> LearnerMemory:
        with self._lock_for(diagnosis.user_id, diagnosis.book_id):
            return self._ingest_diagnosis(diagnosis)

    def _ingest_diagnosis(self, diagnosis: DiagnosisResult) -> LearnerMemory:
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
            point = KnowledgePointMemory(
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
                assessed_mastery_level=result.ai_status,
                user_calibrated_level=result.calibrated_status,
                evidence_ids=list(getattr(result, "evidence_ids", [])),
                reason_codes=list(getattr(result, "reason_codes", [])),
                algorithm_name=str(getattr(result, "algorithm_name", "")),
                algorithm_version=str(getattr(result, "algorithm_version", "")),
            )
            validate_knowledge_point_memory(point)
            points[result.knowledge_point_id] = point
        memory.knowledge_points = list(points.values())
        occurred_at = diagnosis.updated_at or diagnosis.created_at or now
        versions = sorted(
            {
                str(getattr(result, "algorithm_version", ""))
                for result in diagnosis.results
                if getattr(result, "algorithm_version", "")
            }
        )
        return self._apply_event(
            memory,
            MemoryEvent(
                event_id=f"diagnosis:{diagnosis.diagnosis_id}:confirmed",
                user_id=memory.user_id,
                learning_domain=memory.learning_domain,
                event_type=MemoryEventType.DIAGNOSIS_CONFIRMED,
                source_type="formal_assessment",
                occurred_at=occurred_at,
                payload={
                    "diagnosis_id": diagnosis.diagnosis_id,
                    "diagnosis_summary": memory.diagnosis_summary,
                    "results": common_api.serialization.to_data(diagnosis.results),
                    "calibration": diagnosis.calibration,
                    "calibration_reason": diagnosis.calibration_reason,
                },
                algorithm_version=",".join(versions),
            ),
        )

    # 完成任务更新记忆
    def ingest_task_completion(
        self,
        *,
        user_id: str,
        learning_domain: str,
        task_id: str,
        knowledge_point_ids: list[str],
        source: str | None = None,
    ) -> LearnerMemory:
        with self._lock_for(user_id, learning_domain):
            return self._ingest_task_completion(
                user_id=user_id,
                learning_domain=learning_domain,
                task_id=task_id,
                knowledge_point_ids=knowledge_point_ids,
                source=source,
            )

    def _ingest_task_completion(
        self,
        *,
        user_id: str,
        learning_domain: str,
        task_id: str,
        knowledge_point_ids: list[str],
        source: str | None = None,
    ) -> LearnerMemory:
        memory = self.get_learner_memory(user_id, learning_domain)
        now = self.repository.now()
        point_ids = list(
            dict.fromkeys(
                str(item)
                for item in knowledge_point_ids
                if item and str(item) != "unknown"
            )
        )
        memory.last_completed_task_id = task_id
        memory.last_activity_at = now
        memory.completed_task_count += 1
        return self._apply_event(
            memory,
            MemoryEvent(
                event_id=f"task:{memory.user_id}:{memory.learning_domain}:{task_id}",
                user_id=memory.user_id,
                learning_domain=memory.learning_domain,
                event_type=MemoryEventType.TASK_COMPLETED,
                source_type="learning_activity",
                occurred_at=now,
                payload={
                    "task_id": task_id,
                    "knowledge_point_ids": point_ids,
                    "source": source or f"task:{task_id}",
                },
            ),
        )

    def mastered_knowledge_point_ids(self, user_id: str, learning_domain: str) -> set[str]:
        mastered = {MASTERY_LEVELS[-1]}
        memory = self.get_learner_memory(user_id, learning_domain)
        return {
            item.knowledge_point_id
            for item in memory.knowledge_points
            if (item.assessed_mastery_level or item.mastery_level) in mastered
            and not (
                item.assessed_mastery_level is None
                and item.source == "learner_profile"
            )
        }

    def knowledge_point_mastery(self, user_id: str, learning_domain: str) -> dict[str, str]:
        memory = self.get_learner_memory(user_id, learning_domain)
        return {item.knowledge_point_id: item.mastery_level for item in memory.knowledge_points}

    def list_for_user(self, user_id: str, learning_domain: str | None = None) -> list[LearnerMemory]:
        return self.repository.list_for_user(user_id, self._domain(learning_domain) if learning_domain else None)
