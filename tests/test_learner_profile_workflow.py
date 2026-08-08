import tempfile
import unittest
from pathlib import Path

from domain.learner_profile_service import LearnerProfileService
from repositories.learner_profile_repository import JsonLearnerProfileRepository
from workflows.learner_profile_workflow import LearnerProfileWorkflow


def profile_payload(background: str = " 学过 Python ") -> dict:
    return {
        "user_id": "user_001",
        "learning_domain": "machine_learning",
        "background": background,
        "self_assessed_level": "basic",
        "known_skill_ids": ["python", "python"],
        "known_skill_note": "NumPy，NumPy",
        "current_confusions": " 过拟合 ",
        "additional_requirements": " 结合代码 ",
        "preferences": {
            "activity_types": ["reading", "quiz", "reading"],
            "content_style": "balanced",
            "difficulty": "adaptive",
            "session_duration_minutes": 30,
            "learning_frequency": "daily",
        },
    }


class LearnerProfileWorkflowTest(unittest.TestCase):
    def build_workflow(self, directory: str) -> tuple[LearnerProfileWorkflow, JsonLearnerProfileRepository]:
        repository = JsonLearnerProfileRepository(Path(directory) / "profiles.json")
        return LearnerProfileWorkflow(repository, LearnerProfileService()), repository

    def test_profile_is_not_saved_before_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow, repository = self.build_workflow(directory)
            draft = workflow.start(profile_payload())
            self.assertEqual(draft["type"], "learner_profile_review")
            self.assertIsNone(repository.get("user_001", "machine_learning"))

    def test_approve_normalizes_and_saves_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow, repository = self.build_workflow(directory)
            draft = workflow.start(profile_payload())
            saved = workflow.review(draft["workflow_id"], action="approve")
            self.assertEqual(saved.background, "学过 Python")
            self.assertEqual(saved.known_skill_ids, ["python", "NumPy"])
            self.assertEqual(repository.get("user_001", "machine_learning").current_confusions, "过拟合")

    def test_edit_reprocesses_fields_and_replaces_existing_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow, repository = self.build_workflow(directory)
            first = workflow.start(profile_payload("旧背景"))
            workflow.review(first["workflow_id"], action="approve")
            second = workflow.start(profile_payload("临时背景"))
            saved = workflow.review(second["workflow_id"], action="edit", corrections={"background": " 新背景 ", "known_skill_ids": []})
            self.assertEqual(saved.background, "新背景")
            self.assertEqual(repository.get("user_001", "machine_learning").background, "新背景")

    def test_reject_does_not_save_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow, repository = self.build_workflow(directory)
            draft = workflow.start(profile_payload())
            self.assertIsNone(workflow.review(draft["workflow_id"], action="reject"))
            self.assertIsNone(repository.get("user_001", "machine_learning"))


if __name__ == "__main__":
    unittest.main()
