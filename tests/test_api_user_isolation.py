from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, ClassVar

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from modules.common.auth import IdentityResolver
from modules.common.errors import AppError, ResourceNotFoundError
from modules.diagnosis.api import build_router as build_diagnosis_router
from modules.learning_plan.api import build_router as build_learning_plan_router
from modules.learning_record.api import build_router as build_learning_record_router
from modules.material_qa.api import build_router as build_material_qa_router
from modules.material_qa.models import MaterialQaAnswer, MaterialQaConversation

JWT_SECRET = "api-user-isolation-test-secret"


def _jwt_segment(value: dict[str, Any]) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _token(subject: str) -> str:
    header = _jwt_segment({"alg": "HS256", "typ": "JWT"})
    payload = _jwt_segment({"sub": subject, "exp": int(time.time()) + 300})
    signature = hmac.new(
        JWT_SECRET.encode(),
        f"{header}.{payload}".encode(),
        hashlib.sha256,
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    return f"{header}.{payload}.{encoded_signature}"


def _headers(user_id: str, *, forged_user_header: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {_token(user_id)}"}
    if forged_user_header is not None:
        headers["X-User-Id"] = forged_user_header
    return headers


class FakeDiagnosisWorkflow:
    def __init__(self) -> None:
        self.owners: dict[str, str] = {}
        self.answers: dict[str, str] = {}

    def start_diagnosis(
        self,
        *,
        user_id: str,
        book_id: str,
        learning_goal: str,
    ) -> dict[str, Any]:
        diagnostic_id = f"diag-{user_id}"
        self.owners[diagnostic_id] = user_id
        return {
            "diagnostic_id": diagnostic_id,
            "questions": [
                {
                    "id": "q-1",
                    "title": "test question",
                    "tag": "kp-1",
                    "book_id": book_id,
                    "knowledge_point_ids": ["kp-1"],
                    "options": [
                        {"id": "A", "text": "answer A"},
                        {"id": "B", "text": "answer B"},
                    ],
                }
            ],
        }

    def _require_owned(self, diagnostic_id: str, actor_user_id: str) -> None:
        if self.owners.get(diagnostic_id) != actor_user_id:
            raise ResourceNotFoundError(
                "diagnosis not found",
                details={"diagnostic_id": diagnostic_id},
            )

    def submit_answer(
        self,
        diagnostic_id: str,
        question_id: str,
        answer: str,
        skipped: bool,
        *,
        actor_user_id: str,
    ) -> dict[str, Any]:
        self._require_owned(diagnostic_id, actor_user_id)
        self.answers[diagnostic_id] = "" if skipped else answer
        return {
            "diagnostic_id": diagnostic_id,
            "question_id": question_id,
            "saved": True,
        }

    async def finish_diagnosis(
        self,
        diagnostic_id: str,
        *,
        actor_user_id: str,
    ) -> dict[str, str]:
        self._require_owned(diagnostic_id, actor_user_id)
        return {
            "level": "basic",
            "accuracy": "100%",
            "confidence": "high",
            "evidence": "one answer",
            "answer_performance": "completed",
            "generated_at": "2026-01-01T00:00:00+00:00",
            "related_scope": "kp-1",
        }


class FakeLearningPlanModule:
    PLAN: ClassVar[dict[str, Any]] = {
        "book": {"id": "ml", "title": "Machine Learning", "shortTitle": "ML"},
        "goal": "learn safely",
        "goalLevel": "basic",
        "tasks": [
            {
                "id": "task-alice",
                "title": "owned task",
                "type": "practice",
                "minutes": 10,
                "status": "todo",
                "reason": "test",
                "description": "test",
            }
        ],
        "advice": [],
        "resources": [],
    }

    def get_saved(
        self,
        *,
        book_id: str,
        diagnostic_id: str | None,
        user_id: str,
    ) -> dict[str, Any]:
        if user_id != "alice" or book_id != "ml":
            # Missing and foreign plans deliberately share one response.
            raise ResourceNotFoundError(
                "learning plan not found",
                details={"book_id": book_id},
            )
        return dict(self.PLAN)


class FakeMaterialQaWorkflow:
    def __init__(self) -> None:
        self.conversations: dict[str, MaterialQaConversation] = {}

    def create_conversation(
        self,
        *,
        book_id: str,
        user_id: str,
    ) -> MaterialQaConversation:
        conversation = MaterialQaConversation(
            conversation_id=f"conversation-{user_id}",
            book_id=book_id,
            user_id=user_id,
            created_at="2026-01-01T00:00:00+00:00",
        )
        self.conversations[conversation.conversation_id] = conversation
        return conversation

    def ask(
        self,
        *,
        conversation_id: str,
        book_id: str,
        question: str,
        source_ids: list[str],
        actor_user_id: str,
        request_id: str | None = None,
    ) -> MaterialQaAnswer:
        conversation = self.conversations.get(conversation_id)
        if (
            conversation is None
            or conversation.user_id != actor_user_id
            or conversation.book_id != book_id
        ):
            raise ResourceNotFoundError(
                "material QA conversation not found",
                details={"conversation_id": conversation_id},
            )
        return MaterialQaAnswer(
            conversation_id=conversation_id,
            answer=f"answer for {question}",
            refused=False,
            citations=[],
            related_knowledge_points=["kp-1"],
            recommended_action="continue",
            request_id=request_id or f"request-{conversation_id}",
        )


class FakeLearningRecordModule:
    def __init__(self) -> None:
        self.queried_users: list[str] = []

    def list_activities(self, user_id: str, **kwargs: Any) -> dict[str, Any]:
        self.queried_users.append(user_id)
        return {
            "records": [],
            "total": 0,
            "page": kwargs["page"],
            "page_size": kwargs["page_size"],
            "has_next": False,
        }


@dataclass
class ApiFakes:
    diagnosis: FakeDiagnosisWorkflow
    material_qa: FakeMaterialQaWorkflow
    learning_record: FakeLearningRecordModule


@pytest.fixture
def api() -> tuple[TestClient, ApiFakes]:
    diagnosis = FakeDiagnosisWorkflow()
    material_qa = FakeMaterialQaWorkflow()
    learning_record = FakeLearningRecordModule()
    identity = IdentityResolver(
        allow_dev_identity=False,
        jwt_secret=JWT_SECRET,
    )
    app = FastAPI()

    @app.exception_handler(AppError)
    async def handle_app_error(_request: Any, error: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"code": error.code, "message": error.message},
        )

    app.include_router(build_diagnosis_router(diagnosis, identity))
    app.include_router(build_learning_plan_router(FakeLearningPlanModule(), identity))
    app.include_router(build_material_qa_router(material_qa, identity))
    app.include_router(
        build_learning_record_router(
            learning_record,
            learning_plan=None,
            identity=identity,
        )
    )
    return TestClient(app), ApiFakes(diagnosis, material_qa, learning_record)


def test_production_jwt_subject_is_the_only_identity_and_alice_flow_works(
    api: tuple[TestClient, ApiFakes],
) -> None:
    client, fakes = api
    alice = _headers("alice", forged_user_header="bob")

    started = client.post(
        "/api/diagnostics/start",
        headers=alice,
        json={"bookId": "ml", "learningGoal": "goal"},
    )
    assert started.status_code == 200
    diagnostic_id = started.json()["diagnosticId"]
    assert fakes.diagnosis.owners[diagnostic_id] == "alice"

    answered = client.post(
        f"/api/diagnostics/{diagnostic_id}/answers",
        headers=alice,
        json={"questionId": "q-1", "answer": "A"},
    )
    finished = client.post(
        f"/api/diagnostics/{diagnostic_id}/finish",
        headers=alice,
    )
    plan = client.get("/api/learning-plans?bookId=ml", headers=alice)
    conversation = client.post(
        "/api/rag/conversations",
        headers=alice,
        json={"bookId": "ml"},
    )
    conversation_id = conversation.json()["conversationId"]
    asked = client.post(
        f"/api/rag/conversations/{conversation_id}/messages",
        headers=alice,
        json={"bookId": "ml", "question": "explain"},
    )
    records = client.get(
        "/api/learning-records?userId=alice",
        headers=alice,
    )

    assert answered.status_code == 200
    assert finished.status_code == 200
    assert plan.status_code == 200
    assert plan.json()["exists"] is True
    assert conversation.status_code == 200
    assert conversation.json()["userId"] == "alice"
    assert asked.status_code == 200
    assert records.status_code == 200
    assert fakes.learning_record.queried_users == ["alice"]


def test_body_and_query_user_id_cannot_override_jwt_subject(
    api: tuple[TestClient, ApiFakes],
) -> None:
    client, fakes = api
    alice = _headers("alice")

    body_mismatch = client.post(
        "/api/diagnostics/start",
        headers=alice,
        json={
            "bookId": "ml",
            "learningGoal": "goal",
            "userId": "bob",
        },
    )
    query_mismatch = client.get(
        "/api/learning-records?userId=bob",
        headers=alice,
    )

    assert body_mismatch.status_code == 403
    assert query_mismatch.status_code == 403
    assert fakes.diagnosis.owners == {}
    assert fakes.learning_record.queried_users == []


def test_foreign_diagnosis_plan_and_qa_resources_are_hidden_as_not_found(
    api: tuple[TestClient, ApiFakes],
) -> None:
    client, _fakes = api
    alice = _headers("alice")
    bob = _headers("bob")

    started = client.post(
        "/api/diagnostics/start",
        headers=alice,
        json={"bookId": "ml", "learningGoal": "goal"},
    )
    diagnostic_id = started.json()["diagnosticId"]
    conversation = client.post(
        "/api/rag/conversations",
        headers=alice,
        json={"bookId": "ml"},
    )
    conversation_id = conversation.json()["conversationId"]

    foreign_answer = client.post(
        f"/api/diagnostics/{diagnostic_id}/answers",
        headers=bob,
        json={"questionId": "q-1", "answer": "A"},
    )
    foreign_finish = client.post(
        f"/api/diagnostics/{diagnostic_id}/finish",
        headers=bob,
    )
    foreign_plan = client.get("/api/learning-plans?bookId=ml", headers=bob)
    foreign_question = client.post(
        f"/api/rag/conversations/{conversation_id}/messages",
        headers=bob,
        json={"bookId": "ml", "question": "read Alice data"},
    )

    assert foreign_answer.status_code == 404
    assert foreign_finish.status_code == 404
    assert foreign_plan.status_code == 404
    assert foreign_question.status_code == 404

    # Failed foreign reads must not break the owner's normal path.
    assert client.post(
        f"/api/diagnostics/{diagnostic_id}/answers",
        headers=alice,
        json={"questionId": "q-1", "answer": "A"},
    ).status_code == 200
    assert client.post(
        f"/api/diagnostics/{diagnostic_id}/finish",
        headers=alice,
    ).status_code == 200
    assert client.post(
        f"/api/rag/conversations/{conversation_id}/messages",
        headers=alice,
        json={"bookId": "ml", "question": "owner question"},
    ).status_code == 200
