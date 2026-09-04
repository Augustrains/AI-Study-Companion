"""MySQL persistence for the learner-profile module's goal/mastery model."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator

from dotenv import load_dotenv

from modules.common.errors import ConfigurationError, ValidationAppError


class MySqlLearnerProfileRepository:
    def __init__(self, *, host: str, port: int, database: str, user: str, password: str) -> None:
        self.config = {"host": host, "port": port, "database": database, "user": user, "password": password, "charset": "utf8mb4"}

    @classmethod
    def from_env(cls) -> "MySqlLearnerProfileRepository":
        load_dotenv(override=False)
        values = {"host": os.getenv("STUDY_COMPANION_DB_HOST"), "database": os.getenv("STUDY_COMPANION_DB_NAME"), "user": os.getenv("STUDY_COMPANION_DB_USER"), "password": os.getenv("STUDY_COMPANION_DB_PASSWORD")}
        if not all(values.values()):
            raise ConfigurationError("MySQL settings are not configured")
        return cls(port=int(os.getenv("STUDY_COMPANION_DB_PORT", "3306")), **values)  # type: ignore[arg-type]

    @contextmanager
    def connection(self) -> Iterator[Any]:
        try:
            import mysql.connector
        except ImportError as exc:
            raise ConfigurationError("mysql-connector-python is not installed") from exc
        connection = mysql.connector.connect(**self.config)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _one(cursor: Any, query: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        cursor.execute(query, params)
        return cursor.fetchone()

    def books(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT id, book_name, description FROM books ORDER BY id")
            return list(cursor.fetchall())

    def knowledge_points(self, book_id: int) -> list[dict[str, Any]]:
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT id, name, knowledge_point_code AS code, description, course_order FROM knowledge_points WHERE book_id = %s ORDER BY course_order, id", (book_id,))
            return list(cursor.fetchall())

    def load(self, user_id: int, book_id: int) -> dict[str, Any] | None:
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            profile = self._one(cursor, "SELECT background, preferred_content_style FROM learner_profile WHERE user_id = %s ORDER BY updated_at DESC, id DESC LIMIT 1", (user_id,))
            goal = self._one(cursor, "SELECT id, goal, aim_level, daily_minutes, start_date, target_date, status FROM learning_goal WHERE user_id = %s AND book_id = %s ORDER BY status ASC, updated_at DESC, id DESC LIMIT 1", (user_id, book_id))
            if profile is None and goal is None:
                return None
            mastery: list[dict[str, Any]] = []
            if goal is not None:
                cursor.execute("SELECT kpm.knowledge_point_id, kp.name, kpm.mastery_score, kpm.aim_score, kpm.confidence, kpm.next_review_at, GREATEST(kpm.aim_score - kpm.mastery_score, 0) AS gap_score FROM knowledge_point_master kpm JOIN knowledge_points kp ON kp.id = kpm.knowledge_point_id WHERE kpm.user_id = %s AND kpm.goal_id = %s ORDER BY kp.course_order, kp.id", (user_id, goal["id"]))
                mastery = list(cursor.fetchall())
            return {"user_id": user_id, "book_id": book_id, "background": (profile or {}).get("background", ""), "preferred_content_style": (profile or {}).get("preferred_content_style", "balanced"), "goal": goal, "mastery": mastery}

    def save(self, payload: dict[str, Any], point_scores: dict[int, dict[str, float]]) -> dict[str, Any]:
        user_id, book_id = int(payload["user_id"]), int(payload["book_id"])
        now = datetime.now().replace(microsecond=0)
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            if self._one(cursor, "SELECT user_id FROM users WHERE user_id = %s", (user_id,)) is None:
                raise ValidationAppError("user_id does not exist", details={"user_id": user_id})
            if self._one(cursor, "SELECT id FROM books WHERE id = %s", (book_id,)) is None:
                raise ValidationAppError("book_id does not exist", details={"book_id": book_id})
            profile = self._one(cursor, "SELECT id FROM learner_profile WHERE user_id = %s ORDER BY updated_at DESC, id DESC LIMIT 1", (user_id,))
            if profile:
                cursor.execute("UPDATE learner_profile SET background = %s, preferred_content_style = %s, updated_at = %s WHERE id = %s", (payload["background"], payload["preferred_content_style"], now, profile["id"]))
            else:
                cursor.execute("INSERT INTO learner_profile (id, user_id, background, preferred_content_style, created_at, updated_at) VALUES (UUID_SHORT(), %s, %s, %s, %s, %s)", (user_id, payload["background"], payload["preferred_content_style"], now, now))
            goal = self._one(cursor, "SELECT id FROM learning_goal WHERE user_id = %s AND book_id = %s AND status = 0 ORDER BY updated_at DESC, id DESC LIMIT 1", (user_id, book_id))
            values = (payload["goal"], payload["aim_level"], payload["daily_minutes"], payload.get("start_date"), payload.get("target_date"), now)
            if goal:
                goal_id = int(goal["id"])
                cursor.execute("UPDATE learning_goal SET goal = %s, aim_level = %s, daily_minutes = %s, start_date = %s, target_date = %s, updated_at = %s WHERE id = %s", (*values, goal_id))
            else:
                cursor.execute("INSERT INTO learning_goal (id, user_id, book_id, goal, aim_level, daily_minutes, start_date, target_date, status, created_at, updated_at) VALUES (UUID_SHORT(), %s, %s, %s, %s, %s, %s, %s, 0, %s, %s)", (user_id, book_id, *values[:-1], now, now))
                created_goal = self._one(cursor, "SELECT id FROM learning_goal WHERE user_id = %s AND book_id = %s AND status = 0 ORDER BY created_at DESC, id DESC LIMIT 1", (user_id, book_id))
                if created_goal is None:
                    raise RuntimeError("created learning goal could not be loaded")
                goal_id = int(created_goal["id"])
            for point_id, scores in point_scores.items():
                existing = self._one(cursor, "SELECT id FROM knowledge_point_master WHERE user_id = %s AND goal_id = %s AND knowledge_point_id = %s ORDER BY updated_at DESC, id DESC LIMIT 1", (user_id, goal_id, point_id))
                values = (scores["mastery_score"], scores["aim_score"], scores["confidence"], now)
                if existing:
                    cursor.execute("UPDATE knowledge_point_master SET mastery_score = %s, aim_score = %s, confidence = %s, updated_at = %s WHERE id = %s", (*values, existing["id"]))
                else:
                    cursor.execute("INSERT INTO knowledge_point_master (id, user_id, goal_id, knowledge_point_id, mastery_score, aim_score, confidence, created_at, updated_at) VALUES (UUID_SHORT(), %s, %s, %s, %s, %s, %s, %s, %s)", (user_id, goal_id, point_id, *values, now))
        return self.load(user_id, book_id) or {}
