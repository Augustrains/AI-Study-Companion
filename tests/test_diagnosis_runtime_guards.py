from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from modules.common.errors import ResourceNotFoundError, WorkflowStateError
from modules.diagnosis.agent import DiagnosticAgent
from modules.diagnosis.models import Question
from modules.diagnosis.services import AssessmentService, DiagnosisResultStore
from modules.diagnosis.workflow import DiagnosisWorkflow
from modules.persistence.checkpoints import CheckpointResource
from modules.persistence.database import Database
from modules.persistence.workflows import WorkflowSessionRepository


class GuardQuestionBank:
    def __init__(self, question_count: int = 2) -> None:
        self.question_count = question_count

    def get_question_inventory(self, _book_id: str) -> dict[str, int]:
        return {f"kp-{index}": 1 for index in range(self.question_count)}

    def get_questions(self, book_id: str, *, question_plan, **_kwargs):
        del question_plan
        questions = [
            Question(
                id=f"q-{index}",
                title=f"Question {index}",
                tag=f"kp-{index}",
                book_id=book_id,
                knowledge_point_ids=[f"kp-{index}"],
                options=[
                    {"id": "A", "text": "correct"},
                    {"id": "B", "text": "incorrect"},
                ],
            )
            for index in range(self.question_count)
        ]
        return questions, {question.id: "A" for question in questions}


def build_workflow(
    *,
    question_count: int = 2,
    result_store: DiagnosisResultStore | None = None,
    checkpointer=None,
    workflow_sessions: WorkflowSessionRepository | None = None,
) -> DiagnosisWorkflow:
    return DiagnosisWorkflow(
        question_bank=GuardQuestionBank(question_count),
        result_store=result_store or DiagnosisResultStore(),
        assessment_service=AssessmentService(),
        diagnostic_agent=DiagnosticAgent(),
        checkpointer=checkpointer,
        workflow_sessions=workflow_sessions,
    )


def test_sqlite_checkpoint_can_restart_finish_and_retry(tmp_path: Path) -> None:
    database_path = tmp_path / "diagnosis.sqlite3"
    checkpoint_path = tmp_path / "diagnosis-checkpoints.sqlite3"

    database = Database(
        f"sqlite+pysqlite:///{database_path}",
        create_schema=True,
    )
    checkpoints = CheckpointResource.open(
        backend="sqlite",
        url=str(checkpoint_path),
    )
    workflow = build_workflow(
        result_store=DiagnosisResultStore(database),
        checkpointer=checkpoints.saver,
        workflow_sessions=WorkflowSessionRepository(database),
    )
    started = workflow.start_diagnosis(
        user_id="alice",
        book_id="ml-001",
        learning_goal="verify restart",
    )
    diagnosis_id = started["diagnostic_id"]
    workflow.submit_answer(
        diagnosis_id,
        "q-0",
        "A",
        actor_user_id="alice",
    )
    checkpoints.close()
    database.close()

    database = Database(
        f"sqlite+pysqlite:///{database_path}",
        create_schema=True,
    )
    checkpoints = CheckpointResource.open(
        backend="sqlite",
        url=str(checkpoint_path),
    )
    workflow = build_workflow(
        result_store=DiagnosisResultStore(database),
        checkpointer=checkpoints.saver,
        workflow_sessions=WorkflowSessionRepository(database),
    )

    first_summary = asyncio.run(
        workflow.finish_diagnosis(diagnosis_id, actor_user_id="alice")
    )
    retry_summary = asyncio.run(
        workflow.finish_diagnosis(diagnosis_id, actor_user_id="alice")
    )
    assert retry_summary == first_summary
    assert first_summary["accuracy"] == "100%"
    assert workflow._state(diagnosis_id)["status"] == "waiting_for_review"

    result = workflow.confirm_diagnosis(
        diagnosis_id,
        actor_user_id="alice",
    )
    assert result is not None
    assert result.user_id == "alice"
    checkpoints.close()
    database.close()

    # Both the graph terminal state and the confirmed result remain retryable
    # after a second process-style reconstruction.
    database = Database(
        f"sqlite+pysqlite:///{database_path}",
        create_schema=True,
    )
    checkpoints = CheckpointResource.open(
        backend="sqlite",
        url=str(checkpoint_path),
    )
    workflow = build_workflow(
        result_store=DiagnosisResultStore(database),
        checkpointer=checkpoints.saver,
        workflow_sessions=WorkflowSessionRepository(database),
    )
    retried_result = workflow.confirm_diagnosis(
        diagnosis_id,
        calibration="lower",
        reason="a retry must not replace the committed result",
        actor_user_id="alice",
    )
    assert retried_result is not None
    assert retried_result.calibration == "same"
    assert asyncio.run(
        workflow.finish_diagnosis(diagnosis_id, actor_user_id="alice")
    ) == first_summary
    checkpoints.close()
    database.close()


def test_diagnosis_serializes_concurrent_answer_updates(tmp_path: Path) -> None:
    checkpoints = CheckpointResource.open(
        backend="sqlite",
        url=str(tmp_path / "concurrent-checkpoints.sqlite3"),
    )
    workflow = build_workflow(
        question_count=8,
        checkpointer=checkpoints.saver,
    )
    diagnosis_id = workflow.start_diagnosis(
        user_id="alice",
        book_id="ml-001",
        learning_goal="concurrent answers",
    )["diagnostic_id"]

    with ThreadPoolExecutor(max_workers=8) as executor:
        saved = list(
            executor.map(
                lambda index: workflow.submit_answer(
                    diagnosis_id,
                    f"q-{index}",
                    "A",
                ),
                range(8),
            )
        )

    assert all(item["saved"] for item in saved)
    assert workflow._state(diagnosis_id)["answers"] == {
        f"q-{index}": "A" for index in range(8)
    }
    checkpoints.close()


def test_finish_and_review_state_guards_are_idempotent() -> None:
    results = DiagnosisResultStore()
    workflow = build_workflow(question_count=1, result_store=results)
    diagnosis_id = workflow.start_diagnosis(
        user_id="alice",
        book_id="ml-001",
        learning_goal="state guards",
    )["diagnostic_id"]

    with pytest.raises(WorkflowStateError):
        workflow.confirm_diagnosis(diagnosis_id)

    workflow.submit_answer(diagnosis_id, "q-0", "A")
    first_summary = asyncio.run(workflow.finish_diagnosis(diagnosis_id))
    assert asyncio.run(workflow.finish_diagnosis(diagnosis_id)) == first_summary

    with pytest.raises(WorkflowStateError):
        workflow.submit_answer(diagnosis_id, "q-0", "B")

    first_result = workflow.confirm_diagnosis(diagnosis_id)
    first_updated_at = first_result.updated_at if first_result is not None else ""
    retry_result = workflow.confirm_diagnosis(
        diagnosis_id,
        calibration="lower",
        reason="must not overwrite the first confirmation",
    )
    assert first_result is not None
    assert retry_result is first_result
    assert retry_result.calibration == "same"
    assert retry_result.updated_at == first_updated_at
    assert workflow.review(diagnosis_id, action="reject") is first_result
    assert asyncio.run(workflow.finish_diagnosis(diagnosis_id)) == first_summary


def test_rejected_review_cannot_be_reopened() -> None:
    results = DiagnosisResultStore()
    workflow = build_workflow(question_count=1, result_store=results)
    diagnosis_id = workflow.start_diagnosis(
        user_id="alice",
        book_id="ml-001",
        learning_goal="reject safely",
    )["diagnostic_id"]
    workflow.submit_answer(diagnosis_id, "q-0", "A")
    asyncio.run(workflow.finish_diagnosis(diagnosis_id))

    assert workflow.review(diagnosis_id, action="reject") is None
    assert workflow.review(diagnosis_id, action="approve") is None
    with pytest.raises(ResourceNotFoundError):
        results.get(diagnosis_id)
