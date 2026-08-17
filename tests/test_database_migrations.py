from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from modules.persistence import tables as _tables  # noqa: F401
from modules.persistence.database import Base, Database
from modules.persistence.schema_migration import (
    SchemaAdoptionError,
    adopt_existing_schema,
)

ROOT = Path(__file__).resolve().parents[1]
APPLICATION_TABLES = {
    "learner_memory_states",
    "memory_events",
    "learner_memory_history",
    "migration_ledger",
    "conversations",
    "conversation_turns",
    "conversation_messages",
    "conversation_summaries",
    "workflow_sessions",
    "context_traces",
    "diagnosis_results",
}


def _config(database_path: Path) -> Config:
    configuration = Config(str(ROOT / "alembic.ini"))
    database_url = f"sqlite+pysqlite:///{database_path}"
    configuration.set_main_option(
        "script_location",
        str(ROOT / "migrations"),
    )
    configuration.set_main_option(
        "sqlalchemy.url",
        database_url,
    )
    # Programmatic callers must be able to pin a disposable database even when
    # the project .env points at a real deployment database.
    configuration.attributes["database_url"] = database_url
    return configuration


def test_upgrade_head_creates_current_schema(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("STUDY_COMPANION_DATABASE_URL", raising=False)
    database_path = tmp_path / "migration.sqlite3"
    configuration = _config(database_path)
    command.upgrade(configuration, "head")

    engine = create_engine(f"sqlite+pysqlite:///{database_path}")
    inspector = inspect(engine)
    assert APPLICATION_TABLES <= set(inspector.get_table_names())

    assert {
        item["name"] for item in inspector.get_indexes("memory_events")
    } == {"ix_memory_events_owner"}
    assert {
        item["name"] for item in inspector.get_indexes("conversation_turns")
    } == {"ix_conversation_turn_owner"}
    assert {
        item["name"] for item in inspector.get_indexes("conversation_messages")
    } == {"ix_messages_conversation"}
    assert {
        item["name"] for item in inspector.get_indexes("workflow_sessions")
    } == {"ix_workflow_owner"}
    assert {
        item["name"] for item in inspector.get_indexes("diagnosis_results")
    } == {"ix_diagnosis_results_owner"}

    assert inspector.get_pk_constraint("conversation_turns")[
        "constrained_columns"
    ] == ["conversation_id", "request_id"]
    assert {
        item["name"]
        for item in inspector.get_unique_constraints("conversation_messages")
    } == {"uq_message_request_role", "uq_message_sequence"}
    assert {
        item["name"]
        for item in inspector.get_unique_constraints("learner_memory_history")
    } == {"uq_memory_history_version"}
    assert {
        item["name"]
        for item in inspector.get_unique_constraints("conversation_turns")
    } == {"uq_conversation_turn_request"}
    foreign_keys = inspector.get_foreign_keys("conversation_turns")
    assert foreign_keys[0]["referred_table"] == "conversations"
    assert foreign_keys[0]["options"] == {"ondelete": "CASCADE"}

    with engine.connect() as connection:
        migration_context = MigrationContext.configure(connection)
        assert compare_metadata(migration_context, Base.metadata) == []
    engine.dispose()


def test_downgrade_base_removes_all_application_tables(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("STUDY_COMPANION_DATABASE_URL", raising=False)
    database_path = tmp_path / "downgrade.sqlite3"
    configuration = _config(database_path)
    command.upgrade(configuration, "head")
    command.downgrade(configuration, "base")

    engine = create_engine(f"sqlite+pysqlite:///{database_path}")
    remaining = set(inspect(engine).get_table_names())
    assert not APPLICATION_TABLES & remaining
    engine.dispose()


def test_explicit_test_database_cannot_be_overridden_by_environment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target_path = tmp_path / "target.sqlite3"
    decoy_path = tmp_path / "must-not-touch.sqlite3"
    monkeypatch.setenv(
        "STUDY_COMPANION_DATABASE_URL",
        f"sqlite+pysqlite:///{decoy_path}",
    )

    command.upgrade(_config(target_path), "head")

    target_engine = create_engine(f"sqlite+pysqlite:///{target_path}")
    assert APPLICATION_TABLES <= set(inspect(target_engine).get_table_names())
    target_engine.dispose()
    assert not decoy_path.exists()


def test_create_all_database_can_be_validated_and_adopted(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy-create-all.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path}"
    Database(database_url, create_schema=True).close()

    revision = adopt_existing_schema(database_url, project_dir=ROOT)

    assert revision == "20260817_0001"
    engine = create_engine(database_url)
    with engine.connect() as connection:
        version = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one()
    assert version == revision
    engine.dispose()
    # A normal upgrade is now a no-op instead of attempting duplicate CREATEs.
    command.upgrade(_config(database_path), "head")


def test_schema_adoption_refuses_incomplete_legacy_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "incomplete.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path}"
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
    engine.dispose()

    with pytest.raises(SchemaAdoptionError, match="missing application tables"):
        adopt_existing_schema(database_url, project_dir=ROOT)

    engine = create_engine(database_url)
    assert "alembic_version" not in inspect(engine).get_table_names()
    engine.dispose()
