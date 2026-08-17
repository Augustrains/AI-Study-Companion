from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import Barrier, Lock
from time import sleep

import pytest

from modules.common.errors import ConflictError, ResourceNotFoundError
from modules.conversation.models import ConversationTurn
from modules.conversation.repository import SqlConversationRepository
from modules.conversation.service import ConversationService
from modules.persistence.database import Database


def _service(path: Path) -> tuple[Database, ConversationService]:
    database = Database(f"sqlite+pysqlite:///{path}", create_schema=True)
    return database, ConversationService(SqlConversationRepository(database))


def test_turn_survives_restart_and_completed_response_is_reused(
    tmp_path: Path,
) -> None:
    path = tmp_path / "restart.sqlite3"
    database, service = _service(path)
    conversation = service.create(
        user_id="u1",
        book_id="ml",
        mode="material_qa",
    )
    pending = service.begin_turn(
        conversation.conversation_id,
        actor_user_id="u1",
        book_id="ml",
        request_id="req-1",
        question="What is regression?",
    )
    assert pending.status == "pending"
    assert pending.response == {}
    database.close()

    reopened_database, reopened = _service(path)
    calls = 0

    def answer(_turn: ConversationTurn) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"answer": "A supervised learning method."}

    completed = reopened.run_turn(
        conversation.conversation_id,
        actor_user_id="u1",
        book_id="ml",
        request_id="req-1",
        question="What is regression?",
        operation=answer,
    )
    assert completed.status == "completed"
    assert completed.response == {"answer": "A supervised learning method."}
    assert completed.attempt_count == 1
    reopened_database.close()

    final_database, final_service = _service(path)
    reused = final_service.run_turn(
        conversation.conversation_id,
        actor_user_id="u1",
        book_id="ml",
        request_id="req-1",
        question="What is regression?",
        operation=answer,
    )
    assert reused.status == "completed"
    assert reused.response == completed.response
    assert reused.attempt_count == 1
    assert calls == 1
    final_database.close()


def test_turn_idempotency_question_and_response_conflicts(tmp_path: Path) -> None:
    database, service = _service(tmp_path / "idempotency.sqlite3")
    conversation = service.create(user_id="u1", book_id="ml", mode="material_qa")
    first = service.begin_turn(
        conversation.conversation_id,
        actor_user_id="u1",
        book_id="ml",
        request_id="req-1",
        question="Question one",
    )
    duplicate = service.begin_turn(
        conversation.conversation_id,
        actor_user_id="u1",
        book_id="ml",
        request_id="req-1",
        question="Question one",
    )
    assert duplicate.created_at == first.created_at
    with pytest.raises(ConflictError):
        service.begin_turn(
            conversation.conversation_id,
            actor_user_id="u1",
            book_id="ml",
            request_id="req-1",
            question="Changed question",
        )

    completed = service.complete_turn(
        conversation.conversation_id,
        actor_user_id="u1",
        book_id="ml",
        request_id="req-1",
        response={"answer": "one"},
    )
    same = service.complete_turn(
        conversation.conversation_id,
        actor_user_id="u1",
        book_id="ml",
        request_id="req-1",
        response={"answer": "one"},
    )
    assert same.status == "completed"
    assert same.response == completed.response
    with pytest.raises(ConflictError):
        service.complete_turn(
            conversation.conversation_id,
            actor_user_id="u1",
            book_id="ml",
            request_id="req-1",
            response={"answer": "changed"},
        )
    assert service.fail_turn(
        conversation.conversation_id,
        actor_user_id="u1",
        book_id="ml",
        request_id="req-1",
        response={"error_type": "late"},
    ).status == "completed"
    database.close()


def test_failed_turn_retries_and_same_process_executes_operation_once(
    tmp_path: Path,
) -> None:
    database, service = _service(tmp_path / "retry.sqlite3")
    conversation = service.create(user_id="u1", book_id="ml", mode="material_qa")

    def fail(_turn: ConversationTurn) -> dict[str, object]:
        raise RuntimeError("agent failed")

    with pytest.raises(RuntimeError, match="agent failed"):
        service.run_turn(
            conversation.conversation_id,
            actor_user_id="u1",
            book_id="ml",
            request_id="req-failed",
            question="Retry me",
            operation=fail,
        )
    failed = service.turn(
        conversation.conversation_id,
        actor_user_id="u1",
        book_id="ml",
        request_id="req-failed",
    )
    assert failed.status == "failed"
    assert failed.attempt_count == 1
    retried = service.run_turn(
        conversation.conversation_id,
        actor_user_id="u1",
        book_id="ml",
        request_id="req-failed",
        question="Retry me",
        operation=lambda _turn: {"answer": "recovered"},
    )
    assert retried.status == "completed"
    assert retried.attempt_count == 2

    barrier = Barrier(8)
    counter_lock = Lock()
    calls = 0

    def operation(_turn: ConversationTurn) -> dict[str, object]:
        nonlocal calls
        with counter_lock:
            calls += 1
        sleep(0.02)
        return {"answer": "shared"}

    def invoke(_index: int) -> ConversationTurn:
        barrier.wait()
        return service.run_turn(
            conversation.conversation_id,
            actor_user_id="u1",
            book_id="ml",
            request_id="req-concurrent",
            question="Only once",
            operation=operation,
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(invoke, range(8)))
    assert calls == 1
    assert {item.status for item in results} == {"completed"}
    assert {item.response["answer"] for item in results} == {"shared"}
    database.close()


def test_sqlite_begin_race_and_active_lease_never_expose_integrity_error(
    tmp_path: Path,
) -> None:
    path = tmp_path / "lease.sqlite3"
    database_a, service = _service(path)
    conversation = service.create(user_id="u1", book_id="ml", mode="material_qa")
    database_b = Database(f"sqlite+pysqlite:///{path}", create_schema=True)
    repository_a = service.repository
    repository_b = SqlConversationRepository(database_b)
    barrier = Barrier(2)

    def begin(repository: SqlConversationRepository) -> ConversationTurn:
        barrier.wait()
        now = repository.now()
        return repository.begin_turn(
            ConversationTurn(
                conversation_id=conversation.conversation_id,
                request_id="req-race",
                user_id="u1",
                book_id="ml",
                question="same question",
                created_at=now,
                updated_at=now,
            )
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(begin, [repository_a, repository_b]))
    assert [item.status for item in results] == ["pending", "pending"]

    now = repository_a.now()
    expiry = (datetime.fromisoformat(now) + timedelta(minutes=5)).isoformat()
    claimed = repository_a.claim_turn(
        conversation_id=conversation.conversation_id,
        request_id="req-race",
        actor_user_id="u1",
        book_id="ml",
        execution_token="worker-a",
        lease_expires_at=expiry,
        updated_at=now,
    )
    assert claimed.execution_token == "worker-a"
    with pytest.raises(ConflictError, match="already in progress"):
        repository_b.claim_turn(
            conversation_id=conversation.conversation_id,
            request_id="req-race",
            actor_user_id="u1",
            book_id="ml",
            execution_token="worker-b",
            lease_expires_at=expiry,
            updated_at=repository_b.now(),
        )
    database_b.close()
    database_a.close()


def test_turn_operations_are_hidden_from_other_users(tmp_path: Path) -> None:
    database, service = _service(tmp_path / "owners.sqlite3")
    conversation = service.create(user_id="alice", book_id="ml", mode="material_qa")
    service.begin_turn(
        conversation.conversation_id,
        actor_user_id="alice",
        book_id="ml",
        request_id="req-1",
        question="private",
    )
    for operation in (
        lambda: service.begin_turn(
            conversation.conversation_id,
            actor_user_id="bob",
            book_id="ml",
            request_id="req-1",
            question="private",
        ),
        lambda: service.turn(
            conversation.conversation_id,
            actor_user_id="bob",
            book_id="ml",
            request_id="req-1",
        ),
        lambda: service.complete_turn(
            conversation.conversation_id,
            actor_user_id="bob",
            book_id="ml",
            request_id="req-1",
            response={"answer": "stolen"},
        ),
        lambda: service.fail_turn(
            conversation.conversation_id,
            actor_user_id="bob",
            book_id="ml",
            request_id="req-1",
        ),
    ):
        with pytest.raises(ResourceNotFoundError):
            operation()
    database.close()


def test_concurrent_message_turns_stay_atomic_and_idempotent(tmp_path: Path) -> None:
    database, service = _service(tmp_path / "message-pairs.sqlite3")
    conversation = service.create(user_id="u1", book_id="ml", mode="material_qa")

    def append(index: int):
        return service.append_turn_messages(
            conversation.conversation_id,
            actor_user_id="u1",
            book_id="ml",
            request_id=f"req-{index}",
            question=f"question {index}",
            answer=f"answer {index}",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(append, range(12)))
    messages = service.messages(
        conversation.conversation_id,
        actor_user_id="u1",
        book_id="ml",
    )
    assert [item.sequence_no for item in messages] == list(range(1, 25))
    for index in range(0, len(messages), 2):
        user_message, assistant_message = messages[index : index + 2]
        assert (user_message.role, assistant_message.role) == ("user", "assistant")
        assert user_message.request_id == assistant_message.request_id

    first_pair = append(0)
    second_pair = append(0)
    assert [item.message_id for item in second_pair] == [
        item.message_id for item in first_pair
    ]
    with pytest.raises(ConflictError):
        service.append_turn_messages(
            conversation.conversation_id,
            actor_user_id="u1",
            book_id="ml",
            request_id="req-0",
            question="question 0",
            answer="changed answer",
        )
    database.close()
