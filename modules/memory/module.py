from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .models import LongTermMemory
from .repository import JsonMemoryRepository
from .rules import validate_memory

if TYPE_CHECKING:
    from modules.diagnosis.models import DiagnosisResult


class MemoryModule:
    """Owns durable memories derived from completed learning activities."""

    def __init__(self, repository: JsonMemoryRepository) -> None:
        self.repository = repository

    def ingest_diagnosis(self, diagnosis: DiagnosisResult) -> list[LongTermMemory]:
        from modules.diagnosis.models import STATUSES

        domain = diagnosis.book_id
        source = f"diagnostic:{diagnosis.diagnosis_id}"
        answer_records = diagnosis.answer_records
        total = len(answer_records)
        correct = sum(bool(item.get("is_correct")) for item in answer_records)
        memories: list[LongTermMemory] = []

        overall_level = max(
            (result.ai_status for result in diagnosis.results),
            key=lambda status: STATUSES.index(status),
            default=STATUSES[0],
        )
        memories.append(
            self._upsert(
                diagnosis.user_id,
                domain,
                "diagnosis_summary",
                diagnosis.diagnosis_id,
                {
                    "diagnostic_id": diagnosis.diagnosis_id,
                    "accuracy": round(correct / total * 100) if total else 0,
                    "correct_count": correct,
                    "total_count": total,
                    "level": overall_level,
                    "knowledge_points": [
                        {
                            "tag": result.knowledge_point_id,
                            "level": result.calibrated_status or result.ai_status,
                            "correct": result.correct,
                            "total": result.total,
                        }
                        for result in diagnosis.results
                    ],
                },
                1.0 if total else 0.0,
                source,
            )
        )

        for result in diagnosis.results:
            status = result.calibrated_status or result.ai_status
            memories.append(
                self._upsert(
                    diagnosis.user_id,
                    domain,
                    "knowledge_state",
                    result.knowledge_point_id,
                    status,
                    result.correct / result.total if result.total else 0.0,
                    source,
                )
            )
        return memories

    def sync_learner_profile(self, profile: Any) -> list[LongTermMemory]:
        """Initialize or replace memories derived from a confirmed profile."""
        domain = {"machine_learning": "ml-001", "deep_learning": "dl-001"}.get(
            str(profile.learning_domain), str(profile.learning_domain)
        )
        source = f"learner_profile:{profile.user_id}:{domain}"
        current = self.list_for_user(profile.user_id, domain)
        known = {str(item) for item in profile.known_skill_ids if item}
        # Remove profile-derived knowledge states no longer present after an edit.
        for item in current:
            if item.memory_type == "knowledge_state" and item.source == source and item.key not in known:
                self.repository.remove(item.id)

        memories = [
            self._upsert(
                profile.user_id,
                domain,
                "learner_profile",
                "profile",
                {
                    "background": profile.background,
                    "self_assessed_level": profile.self_assessed_level,
                    "known_skill_note": profile.known_skill_note,
                    "current_confusions": profile.current_confusions,
                    "additional_requirements": profile.additional_requirements,
                    "preferences": profile.preferences.to_dict() if hasattr(profile.preferences, "to_dict") else profile.preferences.__dict__,
                },
                1.0,
                source,
            )
        ]
        memories.extend(
            self._upsert(profile.user_id, domain, "knowledge_state", key, "mastered", 0.7, source)
            for key in sorted(known)
        )
        return memories

    def list_for_user(self, user_id: str, learning_domain: str | None = None) -> list[LongTermMemory]:
        return self.repository.list_for_user(user_id, learning_domain)

    def ingest_task_completion(
        self,
        *,
        user_id: str,
        learning_domain: str,
        task_id: str,
        knowledge_point_ids: list[str],
        source: str | None = None,
    ) -> list[LongTermMemory]:
        """Update knowledge-state memories after a plan task is completed.

        A completion is evidence of progress, but not by itself proof of mastery;
        therefore an existing state advances by at most one level.
        """
        from modules.diagnosis.models import STATUSES

        existing = {item.key: item for item in self.list_for_user(user_id, learning_domain)}
        updated: list[LongTermMemory] = []
        for key in dict.fromkeys(str(item) for item in knowledge_point_ids if item and str(item) != "unknown"):
            previous = existing.get(key)
            previous_status = str(previous.value) if previous and isinstance(previous.value, str) else STATUSES[0]
            current_index = STATUSES.index(previous_status) if previous_status in STATUSES else 0
            next_status = STATUSES[min(current_index + 1, len(STATUSES) - 1)]
            confidence = max(previous.confidence if previous else 0.0, 0.5)
            updated.append(
                self._upsert(
                    user_id,
                    learning_domain,
                    "knowledge_state",
                    key,
                    next_status,
                    confidence,
                    source or f"task:{task_id}",
                )
            )
        return updated

    def mastered_skill_ids(self, user_id: str, learning_domain: str) -> set[str]:
        """Return knowledge-point-as-skill IDs that have reached mastery."""
        mastered = {"鎺屾彙", "掌握", "mastered", "proficient"}
        return {
            item.key
            for item in self.list_for_user(user_id, learning_domain)
            if item.memory_type == "knowledge_state"
            and str(item.value) in mastered
        }

    def _upsert(self, user_id: str, domain: str, memory_type: str, key: str, value: Any, confidence: float, source: str) -> LongTermMemory:
        memory_id = f"{user_id}:{domain}:{memory_type}:{key}"
        now = self.repository.now()
        existing = next((item for item in self.repository.list_for_user(user_id, domain) if item.id == memory_id), None)
        memory = LongTermMemory(
            id=memory_id,
            user_id=user_id,
            learning_domain=domain,
            memory_type=memory_type,
            key=key,
            value=value,
            confidence=round(confidence, 4),
            source=source,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        validate_memory(memory)
        return self.repository.upsert(memory)
