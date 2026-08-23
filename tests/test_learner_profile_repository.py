import json
import unittest
from pathlib import Path

from modules.common import api as common_api
from modules.learner_profile.models import LearnerProfile, LearningPreferences
from modules.learner_profile.workflow import JsonLearnerProfileRepository
from tests.test_support import test_directory


class LearnerProfileRepositoryTest(unittest.TestCase):
    def test_missing_profile_is_not_created(self) -> None:
        with test_directory("profile-repository-missing") as directory:
            repository = JsonLearnerProfileRepository(
                common_api.json_storage.JsonContentReader(Path(directory) / "profiles.json"),
                common_api.json_storage.JsonStore(),
            )
            with self.assertRaises(common_api.errors.StorageReadError):
                repository.get("user_001")
            with self.assertRaises(common_api.errors.StorageReadError):
                repository.exists("user_001")

    def test_profile_is_saved_and_read_back(self) -> None:
        with test_directory("profile-repository-save") as directory:
            path = Path(directory) / "profiles.json"
            repository = JsonLearnerProfileRepository(
                common_api.json_storage.JsonContentReader(path),
                common_api.json_storage.JsonStore(),
            )
            profile = LearnerProfile(
                user_id="user_001",
                learning_domain="machine_learning",
                background="学过 Python",
                self_assessed_level="basic",
                known_knowledge_point_ids=["python"],
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
        with test_directory("profile-repository-domains") as directory:
            path = Path(directory) / "profiles.json"
            repository = JsonLearnerProfileRepository(
                common_api.json_storage.JsonContentReader(path),
                common_api.json_storage.JsonStore(),
            )
            repository.save(LearnerProfile(user_id="user_001", learning_domain="machine_learning", background="机器学习背景", known_knowledge_point_ids=["python"]))
            repository.save(LearnerProfile(user_id="user_001", learning_domain="reinforcement_learning", background="强化学习背景", known_knowledge_point_ids=["mdp"]))

            self.assertEqual(repository.get("user_001", "machine_learning").background, "机器学习背景")
            self.assertEqual(repository.get("user_001", "reinforcement_learning").background, "强化学习背景")

            repository.save(LearnerProfile(user_id="user_001", learning_domain="machine_learning", background="新画像", known_knowledge_point_ids=[]))
            stored = json.loads(path.read_text(encoding="utf-8"))["user_001"]
            self.assertEqual(stored["machine_learning"]["background"], "新画像")
            self.assertEqual(stored["machine_learning"]["known_knowledge_point_ids"], [])
            self.assertEqual(stored["reinforcement_learning"]["background"], "强化学习背景")


if __name__ == "__main__":
    unittest.main()
