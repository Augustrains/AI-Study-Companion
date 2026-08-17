from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.common import api as common_api
from modules.common.auth import IdentityResolver
from modules.diagnosis.models import (
    AnswerRecord,
    AnswerResult,
    DiagnosisResult,
    KnowledgePointResult,
    Question,
)
from modules.diagnosis.services import DiagnosisResultStore
from modules.learning_plan.module import LearningPlanModule
from modules.learning_record.api import build_router as build_learning_record_router
from modules.learning_record.module import LearningRecordModule
from modules.today_learning.module import TodayLearningModule


def task(task_id: str, *, status: str = "todo") -> dict[str, Any]:
    return {
        "id": task_id,
        "title": task_id,
        "type": "practice",
        "source": "diagnostic",
        "minutes": 10,
        "status": status,
        "reason": "test",
        "description": "test",
        "knowledge_point_ids": ["kp-1"],
    }


def create_plan_module(path: Path, *, memory: object | None = None) -> LearningPlanModule:
    return LearningPlanModule(
        DiagnosisResultStore(),
        path=path,
        memory=memory,
    )


def test_material_task_updates_the_existing_canonical_plan(tmp_path: Path) -> None:
    path = tmp_path / "plans.json"
    module = create_plan_module(path)
    module.create_task_plan(
        user_id="alice",
        book_id="ml",
        diagnostic_id="diag-1",
        task=task("diagnostic-task"),
        goal="goal",
        goal_level="basic",
        plan_key="alice:ml:diag-1",
    )
    module.create_task_plan(
        user_id="alice",
        book_id="ml",
        task={**task("material-task"), "source": "material_qa"},
        goal="goal",
        goal_level="basic",
        plan_key="alice:ml:material",
    )

    raw = common_api.json_storage.JsonContentReader(path).read()
    assert len(raw) == 1
    assert raw["alice:ml:diag-1"]["diagnosticId"] == "diag-1"

    module.complete_task(
        user_id="alice",
        book_id="ml",
        task_id="diagnostic-task",
    )
    latest = module.get_saved(book_id="ml", user_id="alice")
    assert latest is not None
    assert {item["id"]: item["status"] for item in latest["tasks"]} == {
        "diagnostic-task": "completed",
        "material-task": "todo",
    }


def test_legacy_duplicate_snapshots_read_and_update_only_the_newest(
    tmp_path: Path,
) -> None:
    path = tmp_path / "plans.json"
    module = create_plan_module(path)
    old_plan = {
        "book": module._book("ml"),
        "goal": "old",
        "goalLevel": "basic",
        "tasks": [task("diagnostic-task")],
        "advice": [],
        "resources": [],
    }
    newest_plan = {
        **old_plan,
        "goal": "newest",
        "tasks": [task("diagnostic-task"), task("new-task")],
    }
    common_api.json_storage.JsonStore().save(
        path=path,
        content={
            "old": {
                "userId": "alice",
                "bookId": "ml",
                "diagnosticId": "diag-1",
                "plan": old_plan,
            },
            "newest": {
                "userId": "alice",
                "bookId": "ml",
                "diagnosticId": "diag-1",
                "plan": newest_plan,
            },
        },
        mode="overwrite",
    )

    assert module.get_saved(book_id="ml", user_id="alice")["goal"] == "newest"
    module.complete_task(
        user_id="alice",
        book_id="ml",
        plan_id="old",
        task_id="diagnostic-task",
    )

    raw = common_api.json_storage.JsonContentReader(path).read()
    assert raw["old"]["plan"]["tasks"][0]["status"] == "todo"
    assert raw["newest"]["plan"]["tasks"][0]["status"] == "completed"
    assert module.get_saved(book_id="ml", user_id="alice")["tasks"][0][
        "status"
    ] == "completed"


class FailOnceMemory:
    def __init__(self) -> None:
        self.calls = 0

    def ingest_task_completion(self, **_kwargs: Any) -> object:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary memory failure")
        return object()


def test_retry_repairs_memory_after_plan_was_already_completed(tmp_path: Path) -> None:
    memory = FailOnceMemory()
    module = create_plan_module(tmp_path / "plans.json", memory=memory)
    module.create_task_plan(
        user_id="alice",
        book_id="ml",
        task=task("only-task"),
        goal="goal",
        goal_level="basic",
    )

    with pytest.raises(RuntimeError, match="temporary memory failure"):
        module.complete_task(user_id="alice", book_id="ml", task_id="only-task")
    assert module.get_saved(book_id="ml", user_id="alice")["tasks"][0][
        "status"
    ] == "completed"

    retried = module.complete_task(
        user_id="alice",
        book_id="ml",
        task_id="only-task",
    )
    assert retried["alreadyCompleted"] is True
    assert retried["memoryUpdated"] is True
    assert memory.calls == 2


def test_today_and_lookup_keep_a_fully_completed_plan_visible(tmp_path: Path) -> None:
    plan_module = create_plan_module(tmp_path / "plans.json")
    plan_module.create_task_plan(
        user_id="alice",
        book_id="ml",
        task=task("only-task"),
        goal="goal",
        goal_level="basic",
    )
    plan_module.complete_task(user_id="alice", book_id="ml", task_id="only-task")

    saved = plan_module.get_saved(book_id="ml", user_id="alice")
    assert saved is not None
    assert saved["status"] == "completed"

    records = LearningRecordModule(path=tmp_path / "activities.json")
    today = TodayLearningModule(plan_module, records, diagnosis=None)  # type: ignore[arg-type]
    payload = today.get_today_learning(user_id="alice", book_id="ml")
    assert payload["taskSummary"] == {"completed": 1, "total": 1}
    assert payload["tasks"][0]["status"] == "completed"


class PlanSpy:
    def __init__(self) -> None:
        self.calls = 0

    def complete_task(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        return {}


def test_invalid_learning_event_is_rejected_before_plan_side_effects(
    tmp_path: Path,
) -> None:
    records = LearningRecordModule(path=tmp_path / "activities.json")
    plans = PlanSpy()
    app = FastAPI()
    app.include_router(
        build_learning_record_router(
            records,
            plans,
            IdentityResolver(allow_dev_identity=True),
        )
    )
    client = TestClient(app)

    response = client.post(
        "/api/learning-events",
        headers={"X-User-Id": "alice"},
        json={
            "userId": "alice",
            "taskId": "task-1",
            "taskTitle": "task",
            "eventType": "task_completed",
            "status": "invalid",
        },
    )
    assert response.status_code == 422
    assert plans.calls == 0


def _contains_answer_secret(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = "".join(char for char in str(key).lower() if char.isalnum())
            if normalized.startswith("correctanswer"):
                return True
            if _contains_answer_secret(item):
                return True
    elif isinstance(value, list):
        return any(_contains_answer_secret(item) for item in value)
    return False


def test_diagnosis_learning_record_omits_correct_answer_keys(tmp_path: Path) -> None:
    question = Question(
        id="q-1",
        title="question",
        tag="kp-1",
        knowledge_point_ids=["kp-1"],
        options=[{"id": "A", "text": "wrong"}, {"id": "B", "text": "right"}],
    )
    diagnosis = DiagnosisResult(
        diagnosis_id="diag-1",
        user_id="alice",
        book_id="ml-001",
        learning_goal="goal",
        answer_result=AnswerResult(
            answer_records=[
                AnswerRecord(
                    question=question,
                    submitted_answer="A",
                    correct_answer="B",
                    is_correct=False,
                    skipped=False,
                )
            ],
            total_questions=1,
            answered_questions=1,
            skipped_questions=0,
            correct_questions=0,
            accuracy=0.0,
            confidence="high",
        ),
        results=[
            KnowledgePointResult(
                knowledge_point_id="kp-1",
                ai_status="不会",
                correct=0,
                total=1,
            )
        ],
    )
    records = LearningRecordModule(path=tmp_path / "activities.json")
    activity = records.record_completed_diagnosis(diagnosis)

    assert not _contains_answer_secret(common_api.serialization.to_data(activity))
    stored = common_api.json_storage.JsonContentReader(
        tmp_path / "activities.json"
    ).read()
    assert not _contains_answer_secret(stored)
