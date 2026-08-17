from __future__ import annotations

from pathlib import Path

import pytest

from modules.common.errors import ConflictError
from modules.conversation.repository import SqlConversationRepository
from modules.conversation.service import ConversationService
from modules.material_qa.agent import MaterialQaAgent
from modules.material_qa.models import MaterialQaRetrievalResult
from modules.material_qa.services import MaterialQaService
from modules.material_qa.workflow import MaterialQaWorkflow
from modules.persistence.database import Database


class EmptyRetriever:
    def retrieve(self, **_kwargs) -> MaterialQaRetrievalResult:
        return MaterialQaRetrievalResult(chunks=[])


class CountingClient:
    def __init__(self, *, fail_once: bool = False, must_not_run: bool = False) -> None:
        self.calls = 0
        self.fail_once = fail_once
        self.must_not_run = must_not_run

    def generate(self, _prompt: str) -> str:
        raise AssertionError("role-aware generation is required")

    def generate_messages(self, _messages) -> str:
        self.calls += 1
        if self.must_not_run:
            raise AssertionError("completed turn must not call the Agent again")
        if self.fail_once and self.calls == 1:
            raise RuntimeError("temporary agent failure")
        return '{"refused": false, "answer": "stable answer"}'


def workflow(database: Database, client: CountingClient) -> MaterialQaWorkflow:
    conversations = ConversationService(SqlConversationRepository(database))
    return MaterialQaWorkflow(
        agent=MaterialQaAgent(client),
        retriever=EmptyRetriever(),
        qa_service=MaterialQaService(conversations=conversations),
    )


def test_material_qa_request_is_idempotent_across_restart(tmp_path: Path) -> None:
    path = tmp_path / "qa-turn.sqlite3"
    database = Database(f"sqlite+pysqlite:///{path}", create_schema=True)
    client = CountingClient()
    first_workflow = workflow(database, client)
    conversation = first_workflow.create_conversation(book_id="ml", user_id="alice")

    first = first_workflow.ask(
        conversation_id=conversation.conversation_id,
        book_id="ml",
        question="explain",
        actor_user_id="alice",
        request_id="qa-stable-request",
    )
    duplicate = first_workflow.ask(
        conversation_id=conversation.conversation_id,
        book_id="ml",
        question="explain",
        actor_user_id="alice",
        request_id="qa-stable-request",
    )
    assert first == duplicate
    assert client.calls == 1
    database.close()

    reopened = Database(f"sqlite+pysqlite:///{path}", create_schema=True)
    no_agent = CountingClient(must_not_run=True)
    restarted_workflow = workflow(reopened, no_agent)
    recovered = restarted_workflow.ask(
        conversation_id=conversation.conversation_id,
        book_id="ml",
        question="explain",
        actor_user_id="alice",
        request_id="qa-stable-request",
    )
    messages = restarted_workflow.qa_service.conversations.messages(
        conversation.conversation_id,
        actor_user_id="alice",
        book_id="ml",
    )
    assert recovered == first
    assert no_agent.calls == 0
    assert [(item.sequence_no, item.role) for item in messages] == [
        (1, "user"),
        (2, "assistant"),
    ]
    with pytest.raises(ConflictError):
        restarted_workflow.ask(
            conversation_id=conversation.conversation_id,
            book_id="ml",
            question="different question",
            actor_user_id="alice",
            request_id="qa-stable-request",
        )
    reopened.close()


def test_failed_agent_turn_can_retry_without_partial_messages(tmp_path: Path) -> None:
    database = Database(
        f"sqlite+pysqlite:///{tmp_path / 'qa-retry.sqlite3'}",
        create_schema=True,
    )
    client = CountingClient(fail_once=True)
    qa_workflow = workflow(database, client)
    conversation = qa_workflow.create_conversation(book_id="ml", user_id="alice")

    with pytest.raises(RuntimeError, match="temporary agent failure"):
        qa_workflow.ask(
            conversation_id=conversation.conversation_id,
            book_id="ml",
            question="retry me",
            actor_user_id="alice",
            request_id="qa-retry-request",
        )
    assert qa_workflow.qa_service.conversations.messages(
        conversation.conversation_id,
        actor_user_id="alice",
        book_id="ml",
    ) == []

    answer = qa_workflow.ask(
        conversation_id=conversation.conversation_id,
        book_id="ml",
        question="retry me",
        actor_user_id="alice",
        request_id="qa-retry-request",
    )
    turn = qa_workflow.qa_service.conversations.turn(
        conversation.conversation_id,
        actor_user_id="alice",
        book_id="ml",
        request_id="qa-retry-request",
    )
    assert answer.answer == "stable answer"
    assert client.calls == 2
    assert turn.status == "completed"
    assert turn.attempt_count == 2
    database.close()
