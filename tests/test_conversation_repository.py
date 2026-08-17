from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from modules.common.errors import ConflictError, ResourceNotFoundError
from modules.conversation.models import ConversationSummary
from modules.conversation.repository import SqlConversationRepository
from modules.conversation.service import ConversationService
from modules.persistence.database import Database


def build_service(path: Path) -> tuple[Database, ConversationService]:
    database = Database(f"sqlite+pysqlite:///{path}", create_schema=True)
    return database, ConversationService(SqlConversationRepository(database))


def test_conversation_survives_restart_and_is_owner_scoped(tmp_path: Path) -> None:
    path = tmp_path / "conversation.sqlite3"
    database, service = build_service(path)
    conversation = service.create(user_id="u1", book_id="ml", mode="tutor")
    service.append(
        conversation.conversation_id,
        actor_user_id="u1",
        role="user",
        content="什么是线性回归？",
        request_id="req-1",
    )
    database.close()

    reopened_database, reopened = build_service(path)
    messages = reopened.messages(
        conversation.conversation_id,
        actor_user_id="u1",
    )
    assert [item.content for item in messages] == ["什么是线性回归？"]
    with pytest.raises(ResourceNotFoundError):
        reopened.messages(conversation.conversation_id, actor_user_id="u2")
    reopened_database.close()


def test_message_request_id_is_idempotent(tmp_path: Path) -> None:
    database, service = build_service(tmp_path / "idempotent.sqlite3")
    conversation = service.create(user_id="u1", book_id="ml", mode="tutor")
    first = service.append(
        conversation.conversation_id,
        actor_user_id="u1",
        role="user",
        content="问题一",
        request_id="req-1",
    )
    duplicate = service.append(
        conversation.conversation_id,
        actor_user_id="u1",
        role="user",
        content="问题一",
        request_id="req-1",
    )
    assert duplicate.message_id == first.message_id
    assert len(service.messages(conversation.conversation_id, actor_user_id="u1")) == 1
    with pytest.raises(ConflictError):
        service.append(
            conversation.conversation_id,
            actor_user_id="u1",
            role="user",
            content="被篡改的问题",
            request_id="req-1",
        )
    database.close()


def test_summary_cannot_move_backwards(tmp_path: Path) -> None:
    database, service = build_service(tmp_path / "summary.sqlite3")
    conversation = service.create(user_id="u1", book_id="ml", mode="tutor")
    service.save_summary(
        ConversationSummary(
            conversation_id=conversation.conversation_id,
            summary_version=1,
            through_sequence=10,
            payload={"topics": ["regression"]},
            updated_at="now",
        ),
        actor_user_id="u1",
    )
    with pytest.raises(ConflictError):
        service.save_summary(
            ConversationSummary(
                conversation_id=conversation.conversation_id,
                summary_version=2,
                through_sequence=5,
                payload={},
                updated_at="later",
            ),
            actor_user_id="u1",
        )
    database.close()


def test_concurrent_messages_receive_unique_ordered_sequences(tmp_path: Path) -> None:
    database, service = build_service(tmp_path / "concurrent.sqlite3")
    conversation = service.create(user_id="u1", book_id="ml", mode="tutor")

    def append(index: int) -> None:
        service.append(
            conversation.conversation_id,
            actor_user_id="u1",
            role="user",
            content=f"并发消息 {index}",
            request_id=f"concurrent-{index}",
        )

    with ThreadPoolExecutor(max_workers=6) as executor:
        list(executor.map(append, range(12)))
    messages = service.messages(conversation.conversation_id, actor_user_id="u1")
    assert [item.sequence_no for item in messages] == list(range(1, 13))
    database.close()
