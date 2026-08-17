"""Safely adopt a pre-Alembic database created by ``create_all``.

This command never creates or rewrites application tables.  It stamps the
initial revision only after the existing application-owned schema matches the
current SQLAlchemy metadata exactly.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from modules.common.config import Settings

from . import tables as _tables  # noqa: F401
from .database import Base


class SchemaAdoptionError(RuntimeError):
    """The existing schema cannot safely be marked as the Alembic baseline."""


def _alembic_config(project_dir: Path, database_url: str) -> Config:
    configuration = Config(str(project_dir / "alembic.ini"))
    configuration.set_main_option("script_location", str(project_dir / "migrations"))
    configuration.set_main_option("sqlalchemy.url", database_url)
    configuration.attributes["database_url"] = database_url
    return configuration


def _application_schema_diffs(connection) -> list[object]:
    application_tables = set(Base.metadata.tables)

    def include_object(object_, name, type_, reflected, compare_to):
        del object_, compare_to
        return not (
            type_ == "table" and reflected and name not in application_tables
        )

    context = MigrationContext.configure(
        connection,
        opts={
            "compare_type": True,
            "include_object": include_object,
        },
    )
    return compare_metadata(context, Base.metadata)


def adopt_existing_schema(
    database_url: str,
    *,
    project_dir: str | Path | None = None,
) -> str:
    """Validate a legacy ``create_all`` schema, then stamp the initial revision."""

    root = Path(project_dir or Path(__file__).resolve().parents[2]).resolve()
    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            table_names = set(inspect(connection).get_table_names())
            if "alembic_version" in table_names:
                raise SchemaAdoptionError(
                    "database is already managed by Alembic; run upgrade head instead"
                )
            missing = sorted(set(Base.metadata.tables) - table_names)
            if missing:
                raise SchemaAdoptionError(
                    "existing database is missing application tables: "
                    + ", ".join(missing)
                )
            diffs = _application_schema_diffs(connection)
            if diffs:
                preview = "; ".join(repr(item) for item in diffs[:5])
                raise SchemaAdoptionError(
                    "existing application schema differs from the baseline: " + preview
                )
    finally:
        engine.dispose()

    command.stamp(_alembic_config(root, database_url), "head")
    return "20260817_0001"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and adopt a pre-Alembic Study Companion database."
    )
    parser.add_argument(
        "--database-url",
        help="Database URL; defaults to STUDY_COMPANION_DATABASE_URL/.env.",
    )
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    revision = adopt_existing_schema(args.database_url or settings.database_url)
    print(f"Existing schema adopted at revision {revision}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
