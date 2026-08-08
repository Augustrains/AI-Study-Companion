import json
import tempfile
import unittest
from pathlib import Path

from domain.learner_profile import LearnerProfile, LearningPreferences
from repositories.learner_profile_repository import JsonLearnerProfileRepository


class LearnerProfileRepositoryTest(unittest.TestCase):
    def test_missing_profile_is_not_created(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = JsonLearnerProfileRepository(Path(directory) / "profiles.json")
            self.assertIsNone(repository.get("user_001"))
            self.assertFalse(repository.exists("user_001"))

    def test_profile_is_saved_and_read_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            repository = JsonLearnerProfileRepository(path)
            profile = LearnerProfile(
                user_id="user_001",
                learning_domain="machine_learning",
                background="学过 Python",
                self_assessed_level="basic",
                known_skill_ids=["python"],
                preferences=LearningPreferences(activity_types=["quiz"]),
            )

            repository.save(profile)
            loaded = repository.get("user_001", "machine_learning")

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.background, "学过 Python")
            self.assertEqual(loaded.preferences.activity_types, ["quiz"])
            self.assertTrue(loaded.created_at)
            self.assertTrue(loaded.updated_at)
            self.assertIn("user_001", json.loads(path.read_text(encoding="utf-8")))

    def test_profiles_are_independent_by_learning_domain_and_save_replaces_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            repository = JsonLearnerProfileRepository(path)
            repository.save(LearnerProfile(user_id="user_001", learning_domain="machine_learning", background="机器学习背景", known_skill_ids=["python"]))
            repository.save(LearnerProfile(user_id="user_001", learning_domain="reinforcement_learning", background="强化学习背景", known_skill_ids=["mdp"]))

            self.assertEqual(repository.get("user_001", "machine_learning").background, "机器学习背景")
            self.assertEqual(repository.get("user_001", "reinforcement_learning").background, "强化学习背景")

            repository.save(LearnerProfile(user_id="user_001", learning_domain="machine_learning", background="新画像", known_skill_ids=[]))
            stored = json.loads(path.read_text(encoding="utf-8"))["user_001"]
            self.assertEqual(stored["machine_learning"]["background"], "新画像")
            self.assertEqual(stored["machine_learning"]["known_skill_ids"], [])
            self.assertEqual(stored["reinforcement_learning"]["background"], "强化学习背景")


if __name__ == "__main__":
    unittest.main()
