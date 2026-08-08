import unittest
from pathlib import Path

from agents.diagnostic_agent import DiagnosticAgent
from domain.assessment_service import AssessmentService
from domain.models import LearningSession
from repositories.question_repository import QuestionRepository
from repositories.session_repository import InMemoryLearningSessionRepository
from sdk.llm_client import NullLLMClient
from workflows.diagnosis_workflow import DiagnosisWorkflow


PROJECT_DIR = Path(__file__).parents[1]


class DiagnosisWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = InMemoryLearningSessionRepository()
        self.workflow = DiagnosisWorkflow(
            question_repository=QuestionRepository(PROJECT_DIR / "data" / "questions"),
            session_repository=self.repository,
            assessment_service=AssessmentService(),
            diagnostic_agent=DiagnosticAgent(NullLLMClient()),
        )
        self.session = LearningSession(
            id="learn_test",
            user_id="user_test",
            book_id="machine_learning",
            learning_goal="熟悉",
        )
        self.answers = {
            "ml_q001": "Supervised Learning",
            "ml_q002": "Supervised Learning",
            "ml_q003": "连续值",
            "ml_q004": "类别标签",
        }

    def start_and_submit(self) -> tuple[str, dict]:
        started = self.workflow.start(self.session)
        self.assertEqual(started["type"], "answer_request")
        draft = self.workflow.submit(started["diagnosis_id"], self.answers)
        self.assertEqual(draft["type"], "diagnosis_review")
        return started["diagnosis_id"], draft

    def test_diagnosis_is_not_committed_before_review(self) -> None:
        self.start_and_submit()

        saved = self.repository.get(self.session.id)
        self.assertEqual(saved.knowledge_states, {})
        self.assertEqual(saved.diagnosis_history, [])

    def test_edit_commits_diagnosis_and_calibration(self) -> None:
        diagnosis_id, _ = self.start_and_submit()

        diagnosis = self.workflow.review(
            diagnosis_id,
            action="edit",
            calibrations={"linear_regression": "熟悉"},
        )

        self.assertIsNotNone(diagnosis)
        saved = self.repository.get(self.session.id)
        self.assertEqual(saved.knowledge_states["supervised_learning"], "掌握")
        self.assertEqual(saved.knowledge_states["linear_regression"], "熟悉")
        self.assertEqual(len(saved.diagnosis_history), 1)
        self.assertEqual(len(saved.calibration_history), 1)
        self.assertEqual(
            saved.calibration_history[0]["previous_status"], "基本了解"
        )

    def test_reject_does_not_commit_diagnosis(self) -> None:
        diagnosis_id, _ = self.start_and_submit()

        diagnosis = self.workflow.review(diagnosis_id, action="reject")

        self.assertIsNone(diagnosis)
        saved = self.repository.get(self.session.id)
        self.assertEqual(saved.knowledge_states, {})
        self.assertEqual(saved.diagnosis_history, [])


if __name__ == "__main__":
    unittest.main()

