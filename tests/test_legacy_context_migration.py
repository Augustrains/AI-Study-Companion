from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from modules.common.errors import StorageReadError
from modules.memory.events import MemoryEvent, MemoryEventType
from modules.memory.legacy_migration import (
    LEGACY_PROFILE_CONTEXT_MIGRATION_NAME,
    LEGACY_PROFILE_CONTEXT_MIGRATION_VERSION,
    LegacyProfileContextMigration,
)
from modules.memory.models import KnowledgePointMemory, LearnerMemory
from modules.memory.module import MemoryModule
from modules.memory.sql_repository import SqlMemoryRepository
from modules.persistence.database import Database
from modules.persistence.tables import MigrationLedgerRow


def _profile(
    user_id: str,
    *,
    learning_domain: str = "machine_learning",
    updated_at: str = "",
    known: list[str] | None = None,
    unknown: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "learning_domain": learning_domain,
        "updated_at": updated_at,
        "self_assessed_level": "beginner",
        "known_knowledge_point_ids": known or [],
        "unknown_knowledge_point_ids": unknown or [],
        "current_confusions": "linear algebra",
        "preferences": {
            "activity_types": ["quiz"],
            "content_style": "concise",
            "difficulty": "adaptive",
            "session_duration_minutes": 20,
            "learning_frequency": "daily",
        },
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _build_runtime(path: Path) -> tuple[Database, SqlMemoryRepository, MemoryModule]:
    database = Database(f"sqlite+pysqlite:///{path}", create_schema=True)
    repository = SqlMemoryRepository(database)
    return database, repository, MemoryModule(repository)


def _ledger_row(database: Database) -> MigrationLedgerRow | None:
    with database.session() as session:
        return session.get(
            MigrationLedgerRow,
            (
                LEGACY_PROFILE_CONTEXT_MIGRATION_NAME,
                LEGACY_PROFILE_CONTEXT_MIGRATION_VERSION,
            ),
        )


def test_backfill_is_versioned_idempotent_and_survives_restart(
    tmp_path: Path,
) -> None:
    profiles_path = tmp_path / "profiles"
    _write_json(
        profiles_path / "learner_profiles.json",
        {
            "u1": {
                "machine_learning": _profile(
                    "u1",
                    known=["kp-known"],
                    unknown=["kp-unknown"],
                )
            }
        },
    )
    database_path = tmp_path / "context.sqlite3"
    database, repository, memory = _build_runtime(database_path)

    first = LegacyProfileContextMigration(
        database=database,
        memory=memory,
        profiles_path=profiles_path,
    ).run()
    assert first.already_completed is False
    assert first.scanned_files == 1
    assert first.discovered_profiles == 1
    assert first.migrated_profiles == 1
    saved = memory.get_learner_memory("u1", "ml-001")
    assert saved.state_version == 1
    assert saved.self_reported_known_knowledge_point_ids == ["kp-known"]
    assert saved.self_reported_unknown_knowledge_point_ids == ["kp-unknown"]
    assert len(repository.list_events("u1", "ml-001")) == 1
    row = _ledger_row(database)
    assert row is not None
    assert row.version == LEGACY_PROFILE_CONTEXT_MIGRATION_VERSION
    assert row.details == {"scanned_files": 1, "profile_count": 1}
    database.close()

    reopened, reopened_repository, reopened_memory = _build_runtime(database_path)
    second = LegacyProfileContextMigration(
        database=reopened,
        memory=reopened_memory,
        profiles_path=profiles_path,
    ).run()
    assert second.already_completed is True
    assert second.migrated_profiles == 0
    assert reopened_repository.state_version("u1", "ml-001") == 1
    assert len(reopened_repository.list_events("u1", "ml-001")) == 1
    reopened.close()


def test_profile_backfill_does_not_replace_formal_diagnosis_mastery(
    tmp_path: Path,
) -> None:
    database, repository, memory = _build_runtime(tmp_path / "formal.sqlite3")
    formal_point = KnowledgePointMemory(
        knowledge_point_id="kp-formal",
        mastery_level="掌握",
        mastery_score=0.91,
        confidence=0.88,
        assessed_mastery_level="掌握",
        updated_at="2026-08-17T00:00:00+00:00",
        update_count=1,
        source="diagnostic:diag-1",
    )
    repository.apply_event(
        LearnerMemory(
            user_id="u1",
            learning_domain="ml-001",
            knowledge_points=[formal_point],
        ),
        MemoryEvent(
            event_id="diagnosis:diag-1:confirmed",
            user_id="u1",
            learning_domain="ml-001",
            event_type=MemoryEventType.DIAGNOSIS_CONFIRMED,
            source_type="formal_assessment",
            occurred_at="2026-08-17T00:00:00+00:00",
            payload={"diagnosis_id": "diag-1"},
        ),
        expected_version=0,
    )
    profiles_path = tmp_path / "profiles"
    _write_json(
        profiles_path / "profile.json",
        _profile(
            "u1",
            updated_at="2026-08-17T01:00:00+00:00",
            unknown=["kp-formal"],
        ),
    )

    LegacyProfileContextMigration(
        database=database,
        memory=memory,
        profiles_path=profiles_path,
    ).run()

    saved = memory.get_learner_memory("u1", "machine_learning")
    assert saved.state_version == 2
    assert saved.self_reported_unknown_knowledge_point_ids == ["kp-formal"]
    assert len(saved.knowledge_points) == 1
    point = saved.knowledge_points[0]
    assert point.mastery_level == "掌握"
    assert point.assessed_mastery_level == "掌握"
    assert point.mastery_score == 0.91
    assert point.confidence == 0.88
    assert point.source == "diagnostic:diag-1"
    assert point.update_count == 1
    database.close()


def test_partial_failure_has_no_ledger_and_retry_adds_no_duplicate_event(
    tmp_path: Path,
) -> None:
    profiles_path = tmp_path / "profiles"
    _write_json(profiles_path / "a.json", _profile("u1"))
    _write_json(profiles_path / "b.json", _profile("u2"))
    database, repository, memory = _build_runtime(tmp_path / "retry.sqlite3")

    class FailOnSecondProfile:
        def sync_learner_profile(self, profile: Any) -> LearnerMemory:
            if profile.user_id == "u2":
                raise RuntimeError("injected migration failure")
            return memory.sync_learner_profile(profile)

    with pytest.raises(RuntimeError, match="injected migration failure"):
        LegacyProfileContextMigration(
            database=database,
            memory=FailOnSecondProfile(),  # type: ignore[arg-type]
            profiles_path=profiles_path,
        ).run()

    assert _ledger_row(database) is None
    assert repository.state_version("u1", "ml-001") == 1
    assert len(repository.list_events("u1", "ml-001")) == 1

    retried = LegacyProfileContextMigration(
        database=database,
        memory=memory,
        profiles_path=profiles_path,
    ).run()
    assert retried.already_completed is False
    assert retried.migrated_profiles == 2
    assert _ledger_row(database) is not None
    assert repository.state_version("u1", "ml-001") == 1
    assert len(repository.list_events("u1", "ml-001")) == 1
    assert repository.state_version("u2", "ml-001") == 1
    assert len(repository.list_events("u2", "ml-001")) == 1
    database.close()


def test_invalid_legacy_json_does_not_mark_migration_complete(
    tmp_path: Path,
) -> None:
    profiles_path = tmp_path / "profiles"
    profiles_path.mkdir()
    (profiles_path / "broken.json").write_text("{", encoding="utf-8")
    database, _, memory = _build_runtime(tmp_path / "invalid.sqlite3")

    with pytest.raises(StorageReadError):
        LegacyProfileContextMigration(
            database=database,
            memory=memory,
            profiles_path=profiles_path,
        ).run()

    assert _ledger_row(database) is None
    database.close()
