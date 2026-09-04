"""Persistence adapters for learner goals."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.engine import Engine, RowMapping
from sqlalchemy.exc import SQLAlchemyError

from modules.common import api as common_api
from modules.common.errors import (
    ResourceNotFoundError,
    StorageReadError,
    StorageWriteError,
    ValidationAppError,
)

from .models import TARGET_LEVELS, LearnerGoal


class LearnerGoalRepository(Protocol):
    """Storage operations required by the learner-goal business module."""

    def get(self, *, user_id: str, book_id: str) -> LearnerGoal | None: ...

    def upsert(self, goal: LearnerGoal) -> LearnerGoal: ...


class JsonLearnerGoalRepository:
    """Legacy local-file adapter retained for tests and data export."""

    DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "learner_goals" / "goals.json"

    def __init__(self, path: str | Path | None = None) -> None:
        target = Path(path) if path is not None else self.DEFAULT_PATH
        self.reader = common_api.json_storage.JsonContentReader(target)
        self.store = common_api.json_storage.JsonStore()

    @staticmethod
    def key(user_id: str, book_id: str) -> str:
        return f"{user_id}:{book_id}"

    def _read_all(self) -> dict[str, Any]:
        payload = self.reader.read(allow_missing=True, allow_empty=False)
        if payload == {} or payload is None:
            return {}
        if not isinstance(payload, dict):
            raise common_api.errors.StorageReadError("learner goal resource must be a JSON object")
        return payload

    def get(self, *, user_id: str, book_id: str) -> LearnerGoal | None:
        row = self._read_all().get(self.key(user_id, book_id))
        return LearnerGoal.from_dict(row) if isinstance(row, dict) else None

    def upsert(self, goal: LearnerGoal) -> LearnerGoal:
        self.store.save(
            path=self.reader.path,
            content=goal.to_dict(),
            mode="upsert",
            key_path=[self.key(goal.user_id, goal.book_id)],
        )
        return goal


class MysqlLearnerGoalRepository:
    """Adapt the learner-goal API to the existing ``learning_goal`` table."""

    BOOK_NAMES = {
        "ml": "ML-For-Beginners",
        "dl": "AI-For-Beginners",
    }

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._book_id_cache: dict[str, int] = {}

    @staticmethod
    def _numeric_user_id(user_id: str) -> int:
        try:
            return int(user_id)
        except (TypeError, ValueError) as exc:
            raise ValidationAppError(
                "learner goals require an authenticated database user",
                details={"user_id": user_id},
                cause=exc,
            ) from exc

    def _database_book_id(self, connection: Any, book_id: str) -> int:
        cached = self._book_id_cache.get(book_id)
        if cached is not None:
            return cached

        try:
            numeric_id = int(book_id)
        except (TypeError, ValueError):
            numeric_id = 0

        if numeric_id:
            statement = text("SELECT id FROM books WHERE id = :book_id LIMIT 1")
            parameters = {"book_id": numeric_id}
        else:
            book_name = self.BOOK_NAMES.get(book_id)
            if book_name is None:
                raise ResourceNotFoundError("learner goal book not found", details={"book_id": book_id})
            statement = text("SELECT id FROM books WHERE book_name = :book_name LIMIT 1")
            parameters = {"book_name": book_name}

        row = connection.execute(statement, parameters).mappings().first()
        if row is None:
            raise ResourceNotFoundError("learner goal book not found", details={"book_id": book_id})
        result = int(row["id"])
        self._book_id_cache[book_id] = result
        return result

    @staticmethod
    def _iso_timestamp(value: Any) -> str:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.isoformat()
        return str(value)

    @classmethod
    def _to_goal(cls, row: RowMapping, *, requested_user_id: str, requested_book_id: str) -> LearnerGoal:
        try:
            target_level = TARGET_LEVELS[int(row["aim_level"])]
        except (IndexError, TypeError, ValueError):
            target_level = str(row["goal"])
        return LearnerGoal(
            goal_id=str(row["id"]),
            user_id=requested_user_id,
            book_id=requested_book_id,
            target_level=target_level,
            daily_minutes=int(row["daily_minutes"] or 0),
            target_date=row["target_date"].isoformat() if row["target_date"] else None,
            updated_at=cls._iso_timestamp(row["updated_at"]),
        )

    def get(self, *, user_id: str, book_id: str) -> LearnerGoal | None:
        statement = text(
            "SELECT id, goal, aim_level, daily_minutes, target_date, updated_at FROM learning_goal "
            "WHERE user_id = :user_id AND book_id = :book_id "
            "ORDER BY (status = 0 OR status IS NULL) DESC, updated_at DESC, id DESC LIMIT 1"
        )
        try:
            with self.engine.connect() as connection:
                database_book_id = self._database_book_id(connection, book_id)
                row = connection.execute(
                    statement,
                    {"user_id": self._numeric_user_id(user_id), "book_id": database_book_id},
                ).mappings().first()
        except ResourceNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise StorageReadError("failed to read learner goal", cause=exc) from exc
        return self._to_goal(row, requested_user_id=user_id, requested_book_id=book_id) if row else None

    def upsert(self, goal: LearnerGoal) -> LearnerGoal:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        aim_level = TARGET_LEVELS.index(goal.target_level)
        try:
            with self.engine.begin() as connection:
                database_book_id = self._database_book_id(connection, goal.book_id)
                user_id = self._numeric_user_id(goal.user_id)
                existing_id = connection.execute(
                    text(
                        "SELECT id FROM learning_goal WHERE user_id = :user_id AND book_id = :book_id "
                        "AND (status = 0 OR status IS NULL) "
                        "ORDER BY updated_at DESC, id DESC LIMIT 1 FOR UPDATE"
                    ),
                    {"user_id": user_id, "book_id": database_book_id},
                ).scalar_one_or_none()
                if existing_id is None:
                    result = connection.execute(
                        text(
                            "INSERT INTO learning_goal "
                            "(user_id, book_id, goal, aim_level, daily_minutes, start_date, "
                            "target_date, status, created_at, updated_at) "
                            "VALUES (:user_id, :book_id, :goal, :aim_level, :daily_minutes, "
                            ":start_date, :target_date, 0, :created_at, :updated_at)"
                        ),
                        {
                            "user_id": user_id,
                            "book_id": database_book_id,
                            "goal": goal.target_level,
                            "aim_level": aim_level,
                            "daily_minutes": goal.daily_minutes,
                            "start_date": now.date(),
                            "target_date": goal.target_date,
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
                    existing_id = result.lastrowid
                else:
                    connection.execute(
                        text(
                            "UPDATE learning_goal SET aim_level = :aim_level, "
                            "daily_minutes = :daily_minutes, target_date = :target_date, "
                            "updated_at = :updated_at "
                            "WHERE id = :id"
                        ),
                        {
                            "id": existing_id,
                            "aim_level": aim_level,
                            "daily_minutes": goal.daily_minutes,
                            "target_date": goal.target_date,
                            "updated_at": now,
                        },
                    )
        except ResourceNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise StorageWriteError("failed to save learner goal", cause=exc) from exc
        goal.goal_id = str(existing_id)
        goal.updated_at = now.replace(tzinfo=timezone.utc).isoformat()
        return goal
