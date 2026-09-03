import tempfile
import unittest
from pathlib import Path

from modules.learner_goals.module import LearnerGoalModule, TARGET_LEVELS
from modules.learner_goals.models import LearnerGoal


class _MemoryLearnerGoalRepository:
    def __init__(self) -> None:
        self.goals: dict[tuple[str, str], LearnerGoal] = {}

    def get(self, *, user_id: str, book_id: str) -> LearnerGoal | None:
        return self.goals.get((user_id, book_id))

    def upsert(self, goal: LearnerGoal) -> LearnerGoal:
        self.goals[(goal.user_id, goal.book_id)] = goal
        return goal


class LearnerGoalRepositoryTest(unittest.TestCase):
    def test_module_can_use_an_injected_repository(self) -> None:
        repository = _MemoryLearnerGoalRepository()
        module = LearnerGoalModule(repository=repository)

        saved = module.save(
            user_id="1",
            book_id="ml",
            target_level=TARGET_LEVELS[0],
            daily_minutes=60,
            target_date="2099-12-31",
        )

        self.assertEqual(module.get(user_id="1", book_id="ml"), saved)
        self.assertEqual(module.daily_minutes_budget(user_id="1", book_id="ml"), 60)

    def test_legacy_json_adapter_remains_available(self) -> None:
        path = Path(tempfile.mkdtemp(prefix="learner-goals-")) / "goals.json"
        module = LearnerGoalModule(path)

        module.save(
            user_id="test-user",
            book_id="ml",
            target_level=TARGET_LEVELS[1],
            daily_minutes=30,
            target_date="2099-12-31",
        )

        restored = LearnerGoalModule(path).get(user_id="test-user", book_id="ml")
        self.assertIsNotNone(restored)
        self.assertEqual(restored.daily_minutes, 30)
        self.assertEqual(restored.target_date, "2099-12-31")


if __name__ == "__main__":
    unittest.main()
