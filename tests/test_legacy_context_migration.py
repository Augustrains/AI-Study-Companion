from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from bootstrap import application as application_bootstrap
from modules.common.errors import StorageReadError
from modules.diagnosis.models import (
    AnswerResult,
    DiagnosisResult,
    KnowledgePointResult,
)
from modules.learner_profile.models import LearnerProfile, LearningPreferences
from modules.memory.events import MemoryEvent, MemoryEventType
from modules.memory.legacy_migration import (
    LEGACY_MEMORY_SQL_MIGRATION_NAME,
    LEGACY_MEMORY_SQL_MIGRATION_VERSION,
    LEGACY_PROFILE_CONTEXT_MIGRATION_NAME,
    LEGACY_PROFILE_CONTEXT_MIGRATION_VERSION,
    LegacyMemorySqlMigration,
    LegacyProfileContextMigration,
)
from modules.memory.models import EvidenceSummary, KnowledgePointMemory, LearnerMemory
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


def _ledger_row(
    database: Database,
    migration_name: str = LEGACY_PROFILE_CONTEXT_MIGRATION_NAME,
    version: str = LEGACY_PROFILE_CONTEXT_MIGRATION_VERSION,
) -> MigrationLedgerRow | None:
    with database.session() as session:
        return session.get(
            MigrationLedgerRow,
            (migration_name, version),
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


def test_full_legacy_memory_snapshot_is_preserved_and_idempotent(
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "memory" / "learner_memories.json"
    snapshot = LearnerMemory(
        user_id="u1",
        learning_domain="ml-001",
        knowledge_points=[
            KnowledgePointMemory(
                knowledge_point_id="kp-formal",
                mastery_level="掌握",
                mastery_score=0.93,
                confidence=0.9,
                assessed_mastery_level="掌握",
                updated_at="2026-08-17T01:00:00+00:00",
                update_count=3,
                source="diagnostic:diag-old",
                evidence_ids=["answer-1"],
            )
        ],
        learning_goals=["complete-ml-course", "build-project"],
        diagnosis_summary={"diagnostic_id": "diag-old", "accuracy": 90},
        current_confusions="regularization",
        preferences={"difficulty": "advanced"},
        last_completed_task_id="task-old-8",
        last_activity_at="2026-08-17T02:00:00+00:00",
        completed_task_count=8,
        updated_at="2026-08-17T02:00:00+00:00",
        update_count=12,
    )
    _write_json(legacy_path, {"u1:ml-001": snapshot.to_dict()})
    database_path = tmp_path / "memory.sqlite3"
    database, repository, memory = _build_runtime(database_path)

    first = LegacyMemorySqlMigration(
        database=database,
        memory=memory,
        memory_path=legacy_path,
    ).run()
    assert first.discovered_memories == 1
    assert first.migrated_memories == 1
    saved = memory.get_learner_memory("u1", "ml-001")
    assert saved.learning_goals == ["complete-ml-course", "build-project"]
    assert saved.diagnosis_summary == {
        "diagnostic_id": "diag-old",
        "accuracy": 90,
    }
    assert saved.last_completed_task_id == "task-old-8"
    assert saved.last_activity_at == "2026-08-17T02:00:00+00:00"
    assert saved.completed_task_count == 8
    assert saved.update_count == 12
    assert len(saved.knowledge_points) == 1
    point = saved.knowledge_points[0]
    assert point.assessed_mastery_level == "掌握"
    assert point.mastery_score == 0.93
    assert point.source == "diagnostic:diag-old"
    events = repository.list_events("u1", "ml-001")
    assert len(events) == 1
    assert events[0].event_type == MemoryEventType.LEGACY_SNAPSHOT
    assert _ledger_row(
        database,
        LEGACY_MEMORY_SQL_MIGRATION_NAME,
        LEGACY_MEMORY_SQL_MIGRATION_VERSION,
    ) is not None
    database.close()

    reopened, reopened_repository, reopened_memory = _build_runtime(database_path)
    repeated = LegacyMemorySqlMigration(
        database=reopened,
        memory=reopened_memory,
        memory_path=legacy_path,
    ).run()
    assert repeated.already_completed is True
    assert repeated.migrated_memories == 0
    assert reopened_repository.state_version("u1", "ml-001") == 1
    assert len(reopened_repository.list_events("u1", "ml-001")) == 1
    reopened.close()


def test_partial_memory_failure_has_no_ledger_and_retry_is_idempotent(
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "learner_memories.json"
    first = LearnerMemory(
        user_id="u1",
        learning_domain="ml-001",
        learning_goals=["goal-1"],
    )
    second = LearnerMemory(
        user_id="u2",
        learning_domain="ml-001",
        completed_task_count=4,
    )
    _write_json(
        legacy_path,
        {
            "u1:ml-001": first.to_dict(),
            "u2:ml-001": second.to_dict(),
        },
    )
    database, repository, memory = _build_runtime(tmp_path / "partial.sqlite3")

    class FailOnSecondMemoryRepository:
        def __getattr__(self, name: str) -> Any:
            return getattr(repository, name)

        def apply_event(self, snapshot, event, *, expected_version):
            if event.user_id == "u2":
                raise RuntimeError("injected legacy memory failure")
            return repository.apply_event(
                snapshot,
                event,
                expected_version=expected_version,
            )

    with pytest.raises(RuntimeError, match="injected legacy memory failure"):
        LegacyMemorySqlMigration(
            database=database,
            memory=MemoryModule(FailOnSecondMemoryRepository()),  # type: ignore[arg-type]
            memory_path=legacy_path,
        ).run()

    assert _ledger_row(
        database,
        LEGACY_MEMORY_SQL_MIGRATION_NAME,
        LEGACY_MEMORY_SQL_MIGRATION_VERSION,
    ) is None
    assert repository.state_version("u1", "ml-001") == 1

    LegacyMemorySqlMigration(
        database=database,
        memory=memory,
        memory_path=legacy_path,
    ).run()
    assert repository.state_version("u1", "ml-001") == 1
    assert len(repository.list_events("u1", "ml-001")) == 1
    assert repository.state_version("u2", "ml-001") == 1
    assert _ledger_row(
        database,
        LEGACY_MEMORY_SQL_MIGRATION_NAME,
        LEGACY_MEMORY_SQL_MIGRATION_VERSION,
    ) is not None
    database.close()


def test_invalid_legacy_memory_does_not_write_completion_ledger(
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "learner_memories.json"
    _write_json(
        legacy_path,
        {
            "u1:ml-001": {
                "user_id": "u1",
                "learning_domain": "ml-001",
                "unexpected_field": "must fail",
            }
        },
    )
    database, _, memory = _build_runtime(tmp_path / "invalid-memory.sqlite3")

    with pytest.raises(StorageReadError):
        LegacyMemorySqlMigration(
            database=database,
            memory=memory,
            memory_path=legacy_path,
        ).run()

    assert _ledger_row(
        database,
        LEGACY_MEMORY_SQL_MIGRATION_NAME,
        LEGACY_MEMORY_SQL_MIGRATION_VERSION,
    ) is None
    database.close()


def test_legacy_baseline_adds_post_cutover_sql_evidence_without_double_count(
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "learner_memories.json"
    legacy_point = KnowledgePointMemory(
        knowledge_point_id="kp-shared",
        name="Legacy point name",
        description="Legacy point description",
        mastery_level="了解",
        mastery_score=0.45,
        confidence=0.6,
        memory_status="首次验证",
        memory_stability_days=1.5,
        evidence_summary=EvidenceSummary(
            accepted_evidence_count=3,
            effective_evidence_weight=2.5,
            independent_correct_count=2,
            delayed_correct_count=1,
            delayed_failure_count=1,
            guided_evidence_count=1,
        ),
        updated_at="2026-08-16T01:00:00+00:00",
        update_count=4,
        source="diagnostic:diag-legacy",
        assessed_mastery_level="了解",
        evidence_ids=["legacy-answer", "shared-answer"],
        reason_codes=["legacy-reason", "shared-reason"],
        algorithm_name="legacy-rule",
        algorithm_version="1",
    )
    legacy = LearnerMemory(
        user_id="u1",
        learning_domain="ml-001",
        knowledge_points=[legacy_point],
        learning_goals=["legacy-goal"],
        diagnosis_summary={"diagnostic_id": "diag-legacy"},
        last_completed_task_id="legacy-task-5",
        last_activity_at="2026-08-16T02:00:00+00:00",
        completed_task_count=5,
        updated_at="2026-08-16T02:00:00+00:00",
        update_count=10,
    )
    profile_only_legacy = LearnerMemory(
        user_id="profile-only",
        learning_domain="ml-001",
        knowledge_points=[
            KnowledgePointMemory(
                knowledge_point_id="kp-formal-old",
                mastery_level="掌握",
                mastery_score=0.9,
                confidence=0.85,
                assessed_mastery_level="掌握",
                updated_at="2026-08-16T01:00:00+00:00",
                update_count=2,
                source="diagnostic:diag-profile-old",
            )
        ],
        diagnosis_summary={"diagnostic_id": "diag-profile-old"},
        update_count=5,
    )
    _write_json(
        legacy_path,
        {
            "u1:ml-001": legacy.to_dict(),
            "profile-only:ml-001": profile_only_legacy.to_dict(),
        },
    )
    database, repository, memory = _build_runtime(tmp_path / "merge.sqlite3")

    for user_id in ("u1", "profile-only"):
        memory.sync_learner_profile(
            LearnerProfile(
                user_id=user_id,
                learning_domain="ml-001",
                updated_at=f"2026-08-17T01:00:00+00:00:{user_id}",
                current_confusions="new profile confusion",
                preferences=LearningPreferences(difficulty="adaptive"),
            )
        )
    memory.ingest_diagnosis(
        DiagnosisResult(
            diagnosis_id="diag-current",
            user_id="u1",
            book_id="ml-001",
            learning_goal="post-cutover diagnosis",
            updated_at="2026-08-17T02:00:00+00:00",
            answer_result=AnswerResult(
                answer_records=[],
                total_questions=2,
                answered_questions=2,
                skipped_questions=0,
                correct_questions=2,
                accuracy=1.0,
                confidence="high",
            ),
            results=[
                KnowledgePointResult(
                    knowledge_point_id="kp-shared",
                    ai_status="熟悉",
                    correct=2,
                    total=2,
                    mastery_score=0.78,
                    confidence=0.82,
                    memory_status="延迟复测通过",
                    memory_stability_days=3.0,
                    evidence_summary={
                        "acceptedEvidenceCount": 2,
                        "effectiveEvidenceWeight": 1.75,
                        "independentCorrectCount": 2,
                        "delayedCorrectCount": 1,
                        "delayedFailureCount": 0,
                        "guidedEvidenceCount": 0,
                    },
                    evidence_ids=["shared-answer", "sql-answer"],
                    reason_codes=["shared-reason", "sql-reason"],
                    algorithm_name="current-rule",
                    algorithm_version="2",
                )
            ],
        )
    )
    memory.ingest_task_completion(
        user_id="u1",
        learning_domain="ml-001",
        task_id="sql-task-1",
        knowledge_point_ids=["kp-shared"],
    )

    LegacyMemorySqlMigration(
        database=database,
        memory=memory,
        memory_path=legacy_path,
    ).run()

    merged = memory.get_learner_memory("u1", "ml-001")
    assert merged.completed_task_count == 6
    assert merged.update_count == 13
    assert merged.last_completed_task_id == "sql-task-1"
    assert merged.diagnosis_summary["diagnostic_id"] == "diag-current"
    assert merged.learning_goals == ["legacy-goal"]
    assert merged.current_confusions == "new profile confusion"
    point = merged.knowledge_points[0]
    assert point.mastery_level == "熟悉"
    assert point.mastery_score == 0.78
    assert point.source == "diagnostic:diag-current"
    assert point.name == "Legacy point name"
    assert point.description == "Legacy point description"
    assert point.update_count == 5
    assert point.evidence_summary == EvidenceSummary(
        accepted_evidence_count=5,
        effective_evidence_weight=4.25,
        independent_correct_count=4,
        delayed_correct_count=2,
        delayed_failure_count=1,
        guided_evidence_count=1,
    )
    assert point.evidence_ids == ["legacy-answer", "shared-answer", "sql-answer"]
    assert point.reason_codes == [
        "legacy-reason",
        "shared-reason",
        "sql-reason",
    ]

    profile_only = memory.get_learner_memory("profile-only", "ml-001")
    assert profile_only.diagnosis_summary == {
        "diagnostic_id": "diag-profile-old"
    }
    assert profile_only.knowledge_points[0].mastery_level == "掌握"
    assert profile_only.knowledge_points[0].source == "diagnostic:diag-profile-old"

    before_version = repository.state_version("u1", "ml-001")
    before_event_count = len(repository.list_events("u1", "ml-001"))
    with database.session() as session:
        session.delete(
            session.get(
                MigrationLedgerRow,
                (
                    LEGACY_MEMORY_SQL_MIGRATION_NAME,
                    LEGACY_MEMORY_SQL_MIGRATION_VERSION,
                ),
            )
        )
    LegacyMemorySqlMigration(
        database=database,
        memory=memory,
        memory_path=legacy_path,
    ).run()
    repeated = memory.get_learner_memory("u1", "ml-001")
    assert repeated.completed_task_count == 6
    assert repeated.update_count == 13
    assert repeated.knowledge_points[0].update_count == 5
    assert repeated.knowledge_points[0].evidence_summary.accepted_evidence_count == 5
    assert repository.state_version("u1", "ml-001") == before_version
    assert len(repository.list_events("u1", "ml-001")) == before_event_count
    database.close()


def test_post_cutover_profile_can_explicitly_clear_legacy_declarations(
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "learner_memories.json"
    legacy = LearnerMemory(
        user_id="u-clear",
        learning_domain="ml-001",
        current_confusions="old confusion",
        self_assessed_level="advanced",
        self_reported_known_knowledge_point_ids=["kp-old-known"],
        self_reported_unknown_knowledge_point_ids=["kp-old-unknown"],
        self_reported_knowledge_point_note="old note",
    )
    _write_json(legacy_path, {"u-clear:ml-001": legacy.to_dict()})
    database, _, memory = _build_runtime(tmp_path / "clear.sqlite3")
    memory.sync_learner_profile(
        LearnerProfile(
            user_id="u-clear",
            learning_domain="ml-001",
            updated_at="2026-08-17T08:00:00+00:00",
            self_assessed_level="unknown",
            known_knowledge_point_ids=[],
            unknown_knowledge_point_ids=[],
            known_knowledge_point_note="",
            current_confusions="",
        )
    )

    LegacyMemorySqlMigration(
        database=database,
        memory=memory,
        memory_path=legacy_path,
    ).run()

    merged = memory.get_learner_memory("u-clear", "ml-001")
    assert merged.current_confusions == ""
    assert merged.self_assessed_level == "unknown"
    assert merged.self_reported_known_knowledge_point_ids == []
    assert merged.self_reported_unknown_knowledge_point_ids == []
    assert merged.self_reported_knowledge_point_note == ""
    database.close()


def test_completed_memory_migration_rejects_changed_source_snapshot(
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "learner_memories.json"
    original = LearnerMemory(user_id="u1", learning_domain="ml-001")
    _write_json(legacy_path, {"u1:ml-001": original.to_dict()})
    database, _, memory = _build_runtime(tmp_path / "checksum.sqlite3")
    migration = LegacyMemorySqlMigration(
        database=database,
        memory=memory,
        memory_path=legacy_path,
    )
    migration.run()

    added = LearnerMemory(user_id="u2", learning_domain="ml-001")
    _write_json(
        legacy_path,
        {
            "u1:ml-001": original.to_dict(),
            "u2:ml-001": added.to_dict(),
        },
    )

    with pytest.raises(StorageReadError, match="changed after"):
        migration.run()
    assert memory.get_learner_memory("u2", "ml-001").state_version == 0
    database.close()


def test_bootstrap_propagates_memory_migration_failure_before_profile_sync(
    tmp_path: Path,
    monkeypatch,
) -> None:
    memory_path = tmp_path / "learner_memories.json"
    profile_path = tmp_path / "learner_profiles.json"
    _write_json(memory_path, {})
    _write_json(profile_path, {})
    database = Database(
        f"sqlite+pysqlite:///{tmp_path / 'bootstrap.sqlite3'}",
        create_schema=True,
    )
    profile_migration_called = False

    def fail_memory_migration(**_kwargs):
        raise StorageReadError("legacy memory migration failed")

    def record_profile_migration(**_kwargs):
        nonlocal profile_migration_called
        profile_migration_called = True

    monkeypatch.setattr(
        application_bootstrap,
        "migrate_legacy_memory_to_sql",
        fail_memory_migration,
    )
    monkeypatch.setattr(
        application_bootstrap,
        "migrate_legacy_profiles_to_context_memory",
        record_profile_migration,
    )
    settings = SimpleNamespace(
        memory_path=memory_path,
        profile_path=profile_path,
    )

    with pytest.raises(StorageReadError, match="legacy memory migration failed"):
        application_bootstrap._build_api_dependencies(
            settings,  # type: ignore[arg-type]
            database,
            object(),  # type: ignore[arg-type]
        )
    assert profile_migration_called is False
    database.close()
