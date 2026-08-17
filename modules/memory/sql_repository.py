from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from modules.common import api as common_api
from modules.common.errors import ConflictError
from modules.persistence.database import Database
from modules.persistence.tables import (
    LearnerMemoryHistoryRow,
    LearnerMemoryStateRow,
    MemoryEventRow,
)

from .events import MemoryEvent
from .models import LearnerMemory


class SqlMemoryRepository:
    """Transactional memory snapshot and immutable event repository."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _memory(row: LearnerMemoryStateRow | None) -> LearnerMemory | None:
        if row is None:
            return None
        memory = common_api.serialization.from_data(LearnerMemory, row.payload)
        memory.state_version = row.state_version
        return memory

    def get(self, user_id: str, learning_domain: str) -> LearnerMemory | None:
        with self.database.session() as session:
            return self._memory(
                session.get(LearnerMemoryStateRow, (user_id, learning_domain))
            )

    def state_version(self, user_id: str, learning_domain: str) -> int:
        with self.database.session() as session:
            row = session.get(LearnerMemoryStateRow, (user_id, learning_domain))
            return row.state_version if row else 0

    @contextmanager
    def _event_session(self, event: MemoryEvent) -> Iterator[Session]:
        """Serialize SQLite aggregate writes and normalize uniqueness races."""

        try:
            with self.database.session() as session:
                if self.database.engine.dialect.name.startswith("sqlite"):
                    # SQLite 没有 SELECT FOR UPDATE；在读取版本前取写锁，
                    # 防止两个请求同时基于旧快照生成下一版。
                    session.execute(text("BEGIN IMMEDIATE"))
                yield session
        except IntegrityError as exc:
            raise ConflictError(
                "learner memory was updated concurrently",
                details={
                    "event_id": event.event_id,
                    "user_id": event.user_id,
                    "learning_domain": event.learning_domain,
                },
                cause=exc,
            ) from exc

    def upsert(self, memory: LearnerMemory) -> LearnerMemory:
        with self.database.session() as session:
            row = session.get(
                LearnerMemoryStateRow,
                (memory.user_id, memory.learning_domain),
            )
            next_version = (row.state_version if row else 0) + 1
            memory.state_version = next_version
            payload = memory.to_dict()
            if row is None:
                row = LearnerMemoryStateRow(
                    user_id=memory.user_id,
                    learning_domain=memory.learning_domain,
                    payload=payload,
                    state_version=next_version,
                    updated_at=memory.updated_at or self.now(),
                )
                session.add(row)
            else:
                row.payload = payload
                row.state_version = next_version
                row.updated_at = memory.updated_at or self.now()
            session.add(
                LearnerMemoryHistoryRow(
                    user_id=memory.user_id,
                    learning_domain=memory.learning_domain,
                    state_version=next_version,
                    event_id=None,
                    payload=payload,
                    created_at=self.now(),
                )
            )
        return memory

    def apply_event(
        self,
        memory: LearnerMemory,
        event: MemoryEvent,
        *,
        expected_version: int,
    ) -> LearnerMemory:
        payload_hash = event.payload_hash()
        with self._event_session(event) as session:
            existing = session.get(MemoryEventRow, event.event_id)
            if existing is not None:
                if existing.payload_hash != payload_hash:
                    raise ConflictError(
                        "memory event id already exists with different content",
                        details={"event_id": event.event_id},
                    )
                current = session.get(
                    LearnerMemoryStateRow,
                    (event.user_id, event.learning_domain),
                )
                loaded = self._memory(current)
                return loaded or LearnerMemory(
                    user_id=event.user_id,
                    learning_domain=event.learning_domain,
                )

            statement = select(LearnerMemoryStateRow).where(
                LearnerMemoryStateRow.user_id == event.user_id,
                LearnerMemoryStateRow.learning_domain == event.learning_domain,
            )
            if not self.database.engine.dialect.name.startswith("sqlite"):
                statement = statement.with_for_update()
            row = session.execute(statement).scalar_one_or_none()
            current_version = row.state_version if row else 0
            if current_version != expected_version:
                raise ConflictError(
                    "learner memory was updated concurrently",
                    details={
                        "user_id": event.user_id,
                        "learning_domain": event.learning_domain,
                        "expected_version": expected_version,
                        "current_version": current_version,
                    },
                )

            next_version = current_version + 1
            memory.state_version = next_version
            payload = memory.to_dict()
            session.add(
                MemoryEventRow(
                    event_id=event.event_id,
                    user_id=event.user_id,
                    learning_domain=event.learning_domain,
                    knowledge_point_id=event.knowledge_point_id,
                    event_type=event.event_type,
                    source_type=event.source_type,
                    payload=event.payload,
                    payload_hash=payload_hash,
                    algorithm_version=event.algorithm_version,
                    occurred_at=event.occurred_at,
                    created_at=event.created_at or self.now(),
                )
            )
            if row is None:
                session.add(
                    LearnerMemoryStateRow(
                        user_id=memory.user_id,
                        learning_domain=memory.learning_domain,
                        payload=payload,
                        state_version=next_version,
                        updated_at=memory.updated_at or self.now(),
                    )
                )
            else:
                row.payload = payload
                row.state_version = next_version
                row.updated_at = memory.updated_at or self.now()
            session.add(
                LearnerMemoryHistoryRow(
                    user_id=memory.user_id,
                    learning_domain=memory.learning_domain,
                    state_version=next_version,
                    event_id=event.event_id,
                    payload=payload,
                    created_at=self.now(),
                )
            )
        return memory

    def get_event(self, event_id: str) -> MemoryEvent | None:
        with self.database.session() as session:
            row = session.get(MemoryEventRow, event_id)
            if row is None:
                return None
            return MemoryEvent(
                event_id=row.event_id,
                user_id=row.user_id,
                learning_domain=row.learning_domain,
                knowledge_point_id=row.knowledge_point_id,
                event_type=row.event_type,
                source_type=row.source_type,
                payload=dict(row.payload),
                algorithm_version=row.algorithm_version,
                occurred_at=row.occurred_at,
                created_at=row.created_at,
            )

    def list_events(
        self,
        user_id: str,
        learning_domain: str,
    ) -> list[MemoryEvent]:
        with self.database.session() as session:
            rows = session.execute(
                select(MemoryEventRow)
                .where(
                    MemoryEventRow.user_id == user_id,
                    MemoryEventRow.learning_domain == learning_domain,
                )
                .order_by(MemoryEventRow.occurred_at, MemoryEventRow.event_id)
            ).scalars()
            return [
                MemoryEvent(
                    event_id=row.event_id,
                    user_id=row.user_id,
                    learning_domain=row.learning_domain,
                    knowledge_point_id=row.knowledge_point_id,
                    event_type=row.event_type,
                    source_type=row.source_type,
                    payload=dict(row.payload),
                    algorithm_version=row.algorithm_version,
                    occurred_at=row.occurred_at,
                    created_at=row.created_at,
                )
                for row in rows
            ]

    def list_for_user(
        self,
        user_id: str,
        learning_domain: str | None = None,
    ) -> list[LearnerMemory]:
        with self.database.session() as session:
            statement = select(LearnerMemoryStateRow).where(
                LearnerMemoryStateRow.user_id == user_id
            )
            if learning_domain is not None:
                statement = statement.where(
                    LearnerMemoryStateRow.learning_domain == learning_domain
                )
            rows = session.execute(
                statement.order_by(LearnerMemoryStateRow.learning_domain)
            ).scalars()
            return [self._memory(row) for row in rows if row is not None]
