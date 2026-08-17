from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from modules.common.errors import ConflictError
from modules.memory.events import MemoryEvent, MemoryEventType
from modules.memory.models import KnowledgePointMemory, LearnerMemory
from modules.memory.module import MemoryModule
from modules.memory.sql_repository import SqlMemoryRepository
from modules.persistence.database import Database


def build_repository(path: Path) -> tuple[Database, SqlMemoryRepository]:
    database = Database(f"sqlite+pysqlite:///{path}", create_schema=True)
    return database, SqlMemoryRepository(database)


def test_sql_memory_survives_restart_and_events_are_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "memory.sqlite3"
    database, repository = build_repository(path)
    memory = LearnerMemory(
        user_id="u1",
        learning_domain="ml-001",
        knowledge_points=[
            KnowledgePointMemory(
                knowledge_point_id="kp-1",
                mastery_level="熟悉",
                mastery_score=0.72,
                confidence=0.8,
                assessed_mastery_level="熟悉",
                updated_at="now",
                update_count=1,
                source="diagnostic:diag-1",
            )
        ],
        updated_at=repository.now(),
        update_count=1,
    )
    event = MemoryEvent(
        event_id="diagnosis:diag-1:confirmed",
        user_id="u1",
        learning_domain="ml-001",
        event_type=MemoryEventType.DIAGNOSIS_CONFIRMED,
        source_type="formal_assessment",
        occurred_at="2026-08-17T00:00:00+00:00",
        payload={"diagnosis_id": "diag-1"},
    )
    saved = repository.apply_event(memory, event, expected_version=0)
    assert saved.state_version == 1
    database.close()

    reopened_database, reopened = build_repository(path)
    loaded = reopened.get("u1", "ml-001")
    assert loaded is not None
    assert loaded.knowledge_points[0].assessed_mastery_level == "熟悉"
    duplicate = reopened.apply_event(loaded, event, expected_version=1)
    assert duplicate.state_version == 1
    assert len(reopened.list_events("u1", "ml-001")) == 1
    reopened_database.close()


def test_same_event_id_with_different_payload_is_rejected(tmp_path: Path) -> None:
    database, repository = build_repository(tmp_path / "conflict.sqlite3")
    memory = LearnerMemory(user_id="u1", learning_domain="ml-001")
    first = MemoryEvent(
        event_id="event-1",
        user_id="u1",
        learning_domain="ml-001",
        event_type=MemoryEventType.PROFILE_DECLARED,
        source_type="self_report",
        occurred_at="now",
        payload={"level": "beginner"},
    )
    repository.apply_event(memory, first, expected_version=0)
    changed = MemoryEvent(
        event_id="event-1",
        user_id="u1",
        learning_domain="ml-001",
        event_type=MemoryEventType.PROFILE_DECLARED,
        source_type="self_report",
        occurred_at="later",
        payload={"level": "expert"},
    )
    with pytest.raises(ConflictError):
        repository.apply_event(memory, changed, expected_version=1)
    database.close()


def test_task_completion_does_not_change_or_create_mastery(tmp_path: Path) -> None:
    database, repository = build_repository(tmp_path / "task.sqlite3")
    point = KnowledgePointMemory(
        knowledge_point_id="kp-1",
        mastery_level="了解",
        mastery_score=0.35,
        confidence=0.6,
        assessed_mastery_level="了解",
        evidence_ids=["answer-1"],
        updated_at="now",
        update_count=1,
        source="diagnostic:diag-1",
    )
    repository.upsert(
        LearnerMemory(
            user_id="u1",
            learning_domain="ml-001",
            knowledge_points=[point],
        )
    )
    module = MemoryModule(repository)
    result = module.ingest_task_completion(
        user_id="u1",
        learning_domain="ml",
        task_id="task-1",
        knowledge_point_ids=["kp-1", "kp-new"],
    )
    assert len(result.knowledge_points) == 1
    after = result.knowledge_points[0]
    assert after.mastery_level == "了解"
    assert after.mastery_score == 0.35
    assert after.confidence == 0.6
    assert after.evidence_ids == ["answer-1"]
    assert result.completed_task_count == 1
    database.close()


def test_concurrent_memory_events_for_one_learner_are_serialized(tmp_path: Path) -> None:
    database, repository = build_repository(tmp_path / "concurrent.sqlite3")
    module = MemoryModule(repository)

    def complete(task_id: str) -> None:
        module.ingest_task_completion(
            user_id="u1",
            learning_domain="ml",
            task_id=task_id,
            knowledge_point_ids=["kp-1"],
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(complete, ["task-1", "task-2"]))

    memory = module.get_learner_memory("u1", "ml")
    assert memory.completed_task_count == 2
    assert memory.state_version == 2
    assert {item.event_id for item in repository.list_events("u1", "ml-001")} == {
        "task:u1:ml-001:task-1",
        "task:u1:ml-001:task-2",
    }
    database.close()
