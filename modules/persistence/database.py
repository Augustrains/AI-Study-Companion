from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Declarative base shared by all application-owned tables."""


def _sqlite_path(database_url: str) -> Path | None:
    prefix = "sqlite+pysqlite:///"
    if not database_url.startswith(prefix):
        return None
    value = database_url[len(prefix) :]
    if value in {":memory:", ""}:
        return None
    return Path(value).expanduser().resolve()


class Database:
    """Own the SQLAlchemy engine and short-lived transactional sessions."""

    def __init__(self, database_url: str, *, create_schema: bool = False) -> None:
        path = _sqlite_path(database_url)
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(
            database_url,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        if database_url.startswith("sqlite"):
            event.listen(self.engine, "connect", self._enable_sqlite_foreign_keys)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
            autoflush=False,
        )
        if create_schema:
            self.create_schema()

    @staticmethod
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    def create_schema(self) -> None:
        # Import model modules so all tables are registered on Base.metadata.
        from . import tables as _tables  # noqa: F401

        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def close(self) -> None:
        self.engine.dispose()
