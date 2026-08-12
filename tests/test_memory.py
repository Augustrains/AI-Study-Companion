import unittest
from pathlib import Path

from modules.common import api as common_api
from modules.memory.models import LongTermMemory
from modules.memory.module import MemoryModule
from modules.memory.repository import JsonMemoryRepository
from modules.memory.rules import validate_memory


class MemoryModuleTest(unittest.TestCase):
    def test_memory_uses_common_storage_and_round_trips(self) -> None:
        path = Path(__file__).parent / ".test-data" / "memory-test.json"
        try:
            repository = JsonMemoryRepository(
                reader=common_api.json_storage.JsonContentReader(path),
                store=common_api.json_storage.JsonStore(),
            )
            memory = LongTermMemory(
                id="u1:ml:knowledge_state:regression",
                user_id="u1",
                learning_domain="ml",
                memory_type="knowledge_state",
                key="regression",
                value="掌握",
                confidence=0.8,
                source="diagnostic:d1",
                created_at="2026-01-01T00:00:00+00:00",
                updated_at="2026-01-01T00:00:00+00:00",
            )
            MemoryModule(repository)._upsert(
                memory.user_id,
                memory.learning_domain,
                memory.memory_type,
                memory.key,
                memory.value,
                memory.confidence,
                memory.source,
            )
            saved = repository.list_for_user("u1", "ml")
            self.assertEqual(saved[0].id, memory.id)
            self.assertEqual(saved[0].value, memory.value)
            self.assertEqual(saved[0].confidence, memory.confidence)
        finally:
            path.unlink(missing_ok=True)

    def test_memory_validation_rejects_invalid_confidence(self) -> None:
        with self.assertRaises(common_api.errors.ValidationAppError):
            validate_memory({
                "id": "m1",
                "user_id": "u1",
                "learning_domain": "ml",
                "memory_type": "knowledge_state",
                "key": "regression",
                "value": "掌握",
                "confidence": 1.2,
                "source": "diagnostic:d1",
                "created_at": "now",
                "updated_at": "now",
            })
