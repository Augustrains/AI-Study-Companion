from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

from modules.persistence import tables as _tables  # noqa: F401
from modules.persistence.database import Base

config = context.config
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    return (
        config.attributes.get("database_url")
        or os.getenv("STUDY_COMPANION_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or config.get_main_option("sqlalchemy.url")
    )


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def configure_and_run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        configure_and_run(supplied_connection)
        return

    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = database_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        configure_and_run(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
