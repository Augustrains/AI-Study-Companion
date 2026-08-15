import unittest
from pathlib import Path

from modules.diagnosis.agent import DiagnosticAgent
from modules.diagnosis.models import DiagnosticSession
from modules.diagnosis.services import AssessmentService, DiagnosticSessionStore, QuestionBank
from modules.diagnosis.workflow import DiagnosisWorkflow
from sdk.llm_client import NullLLMClient


PROJECT_DIR = Path(__file__).parents[1]


class DiagnosisWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = DiagnosticSessionStore()
        self.workflow = DiagnosisWorkflow(
            question_bank=QuestionBank(PROJECT_DIR / "data" / "questions"),
            session_store=self.repository,
            assessment_service=AssessmentService(),
            diagnostic_agent=DiagnosticAgent(NullLLMClient()),
        )
        self.session = DiagnosticSession(
            id="diag_test",
            user_id="user_test",
            book_id="machine_learning",
            learning_goal="熟悉",
        )
        self.answers = {
            "ml_q001": "0",
            "ml_q002": "0",
            "ml_q003": "0",
            "ml_q004": "1",
        }

    def start_and_submit(self) -> tuple[str, dict]:
        started = self.workflow.start(self.session)
        self.assertEqual(started["type"], "answer_request")
        draft = self.workflow.submit(started["diagnosis_id"], self.answers)
        self.assertEqual(draft["type"], "diagnosis_review")
        return started["diagnosis_id"], draft

    def test_diagnostic_session_tracks_answers_before_review(self) -> None:
        diagnosis_id, _ = self.start_and_submit()
        saved = self.repository.get(diagnosis_id)
        self.assertEqual(saved.status, "awaiting_review")
        self.assertEqual(saved.answers, self.answers)

    def test_completed_diagnostic_session_stores_result(self) -> None:
        diagnosis_id, _ = self.start_and_submit()
        diagnosis = self.workflow.review(
            diagnosis_id,
            action="edit",
            calibrations={"linear_regression": "熟悉"},
        )

        self.assertIsNotNone(diagnosis)
        saved = self.repository.get(diagnosis_id)
        self.assertEqual(saved.status, "completed")
        self.assertIsNotNone(saved.result)
        self.assertEqual(saved.result["answer_records"][0]["is_correct"], True)

    def test_user_calibration_and_reason_are_preserved_for_planning(self) -> None:
        diagnosis_id, _ = self.start_and_submit()

        diagnosis = self.workflow.confirm_diagnosis(
            diagnosis_id,
            calibration="higher",
            reason="我在实际项目中使用过这个知识点。",
        )

        self.assertIsNotNone(diagnosis)
        saved = self.repository.get(diagnosis_id)
        self.assertEqual(saved.calibration, "higher")
        self.assertEqual(saved.calibration_reason, "我在实际项目中使用过这个知识点。")
        self.assertEqual(saved.result["calibration"]["reason"], "我在实际项目中使用过这个知识点。")

    def test_rejected_diagnostic_session_is_not_completed(self) -> None:
        diagnosis_id, _ = self.start_and_submit()
        diagnosis = self.workflow.review(diagnosis_id, action="reject")

        self.assertIsNone(diagnosis)
        saved = self.repository.get(diagnosis_id)
        self.assertEqual(saved.status, "rejected")
        self.assertIsNone(saved.result)


if __name__ == "__main__":
    unittest.main()
