import unittest
from pathlib import Path

from modules.common import api as common_api
from modules.memory.models import KnowledgePointMemory, LearnerMemory
from modules.memory.module import MemoryModule
from modules.memory.repository import JsonMemoryRepository
from modules.memory.rules import validate_knowledge_point_memory


class MemoryModuleTest(unittest.TestCase):
    def build_repository(self, path: Path) -> JsonMemoryRepository:
        return JsonMemoryRepository(
            reader=common_api.json_storage.JsonContentReader(path),
            store=common_api.json_storage.JsonStore(),
        )

    def test_learner_memory_round_trips(self) -> None:
        path = Path(__file__).parent / ".test-data" / "memory-test.json"
        try:
            repository = self.build_repository(path)
            memory = LearnerMemory(
                user_id="u1",
                learning_domain="ml",
                knowledge_points=[KnowledgePointMemory("regression", mastery_level="掌握", confidence=1.0, updated_at="now", update_count=1, source="learner_profile")],
                updated_at="now",
                update_count=1,
            )
            repository.upsert(memory)
            loaded = repository.get("u1", "ml")
            self.assertEqual(loaded.knowledge_points[0].knowledge_point_id, "regression")
            self.assertEqual(loaded.knowledge_points[0].mastery_level, "掌握")
        finally:
            path.unlink(missing_ok=True)

    def test_profile_sync_keeps_self_report_separate_from_assessed_mastery(self) -> None:
        path = Path(__file__).parent / ".test-data" / "memory-profile.json"
        try:
            repository = self.build_repository(path)
            module = MemoryModule(repository)
            repository.upsert(
                LearnerMemory(
                    user_id="u1",
                    learning_domain="ml-001",
                    knowledge_points=[
                        KnowledgePointMemory(
                            "kp-assessed",
                            mastery_level="熟悉",
                            mastery_score=0.7,
                            confidence=0.8,
                            assessed_mastery_level="熟悉",
                            updated_at="now",
                            update_count=1,
                            source="diagnostic:diag-1",
                        )
                    ],
                )
            )
            profile = type("Profile", (), {
                "user_id": "u1", "learning_domain": "machine_learning",
                "known_knowledge_point_ids": ["kp-1"],
                "unknown_knowledge_point_ids": ["kp-2"],
                "self_assessed_level": "beginner",
                "known_knowledge_point_note": "已掌握基础概念",
                "current_confusions": "",
                "preferences": type("Preferences", (), {"__dict__": {"difficulty": "adaptive"}})(),
            })()
            memory = module.sync_learner_profile(profile)
            point = memory.knowledge_points[0]
            self.assertEqual(point.knowledge_point_id, "kp-assessed")
            self.assertEqual(point.mastery_level, "熟悉")
            self.assertEqual(point.confidence, 0.8)
            self.assertEqual(point.source, "diagnostic:diag-1")
            self.assertEqual(point.update_count, 1)
            self.assertEqual(memory.self_reported_known_knowledge_point_ids, ["kp-1"])
            self.assertEqual(memory.self_reported_unknown_knowledge_point_ids, ["kp-2"])
            self.assertEqual(memory.self_assessed_level, "beginner")
        finally:
            path.unlink(missing_ok=True)

    def test_memory_validation_rejects_invalid_confidence(self) -> None:
        with self.assertRaises(common_api.errors.ValidationAppError):
            validate_knowledge_point_memory({
                "knowledge_point_id": "kp-1",
                "name": "",
                "description": "",
                "mastery_level": "mastered",
                "confidence": 1.2,
                "updated_at": "now",
                "update_count": 1,
                "source": "learner_profile",
            })
