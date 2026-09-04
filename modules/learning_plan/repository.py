"""MySQL reads and writes for the seven-day learning-plan workflow."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from modules.common.errors import ValidationAppError
from modules.learner_profile.repository import MySqlLearnerProfileRepository


class MySqlLearningPlanRepository(MySqlLearnerProfileRepository):
    """Reuses the application's single MySQL configuration and transaction API."""

    def load_weekly_context(self, *, user_id: int, book_id: int) -> dict[str, Any]:
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT id, book_name FROM books WHERE id = %s", (book_id,))
            book = cursor.fetchone()
            if book is None:
                raise ValidationAppError("book_id does not exist", details={"book_id": book_id})
            cursor.execute(
                "SELECT id, goal, aim_level, daily_minutes, start_date, target_date FROM learning_goal "
                "WHERE user_id = %s AND book_id = %s AND status = 0 ORDER BY updated_at DESC, id DESC LIMIT 1",
                (user_id, book_id),
            )
            goal = cursor.fetchone()
            if goal is None:
                raise ValidationAppError("an active learning goal is required", details={"user_id": user_id, "book_id": book_id})
            cursor.execute(
                "SELECT kpm.knowledge_point_id, kp.name AS knowledge_point_name, kp.knowledge_point_code, kp.chapter_id, c.title AS chapter_title, "
                "kp.course_order, kpm.mastery_score, kpm.aim_score, kpm.confidence, kpm.next_review_at, "
                "GREATEST(kpm.aim_score - kpm.mastery_score, 0) AS gap_score "
                "FROM knowledge_point_master kpm "
                "JOIN knowledge_points kp ON kp.id = kpm.knowledge_point_id "
                "LEFT JOIN chapters c ON c.id = kp.chapter_id "
                "WHERE kpm.user_id = %s AND kpm.goal_id = %s "
                "ORDER BY kp.course_order, kp.id",
                (user_id, goal["id"]),
            )
            points = list(cursor.fetchall())
            if not points:
                raise ValidationAppError("knowledge-point mastery records are required", details={"goal_id": goal["id"]})
            cursor.execute(
                "SELECT qkp.knowledge_point_id, da.is_correct "
                "FROM diagnostic_answer da "
                "JOIN diagnostic_session ds ON ds.id = da.session_id "
                "JOIN question_knowledge_points qkp ON qkp.question_id = da.question_id "
                "WHERE ds.user_id = %s AND ds.book_id = %s AND (ds.goal_id = %s OR ds.goal_id IS NULL) "
                "ORDER BY da.created_at ASC, da.id ASC",
                (user_id, book_id, goal["id"]),
            )
            outcomes: dict[int, list[bool]] = {}
            for item in cursor.fetchall():
                outcomes.setdefault(int(item["knowledge_point_id"]), []).append(bool(item["is_correct"]))
            cursor.execute(
                "SELECT qkp.knowledge_point_id, q.id AS question_id "
                "FROM questions q JOIN question_knowledge_points qkp ON qkp.question_id = q.id "
                "WHERE q.book_id = %s AND q.item_type = 'quiz_question' ORDER BY q.id",
                (book_id,),
            )
            question_ids: dict[int, list[int]] = {}
            for item in cursor.fetchall():
                question_ids.setdefault(int(item["knowledge_point_id"]), []).append(int(item["question_id"]))
        return {"user_id": user_id, "book": book, "goal": goal, "points": points, "outcomes": outcomes, "question_ids": question_ids}

    def load_active_weekly_plan(self, *, user_id: int, book_id: int) -> dict[str, Any] | None:
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, goal_id, window_start_date, window_end_date, daily_minutes, adaptive_version "
                "FROM learning_plan WHERE user_id = %s AND book_id = %s AND status = 'active' "
                "ORDER BY updated_at DESC, id DESC LIMIT 1",
                (user_id, book_id),
            )
            plan = cursor.fetchone()
            if plan is None:
                return None
            cursor.execute(
                "SELECT id, title, adaptive_reason, expected_date, generated_version, priority_score "
                "FROM learning_plan_day WHERE plan_id = %s ORDER BY expected_date, id",
                (plan["id"],),
            )
            days = list(cursor.fetchall())
            for day in days:
                cursor.execute(
                    "SELECT id, title, description, status, source, adaptive_reason, item_type, started_at, completed_at "
                    "FROM learning_plan_day_item WHERE learning_plan_day_id = %s ORDER BY id",
                    (day["id"],),
                )
                day["items"] = list(cursor.fetchall())
            return {"plan": plan, "days": days}

    def complete_weekly_plan_item(self, *, user_id: int, item_id: int) -> dict[str, Any]:
        """Complete one task after verifying it belongs to the user's active plan."""
        now = datetime.now().replace(microsecond=0)
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT item.id, item.title, item.status FROM learning_plan_day_item item "
                "JOIN learning_plan_day day ON day.id = item.learning_plan_day_id "
                "JOIN learning_plan plan ON plan.id = day.plan_id "
                "WHERE item.id = %s AND plan.user_id = %s AND plan.status = 'active'",
                (item_id, user_id),
            )
            item = cursor.fetchone()
            if item is None:
                raise ValidationAppError("learning-plan item does not belong to an active user plan", details={"item_id": item_id, "user_id": user_id})
            if item["status"] != "completed":
                self._assert_item_unlocked(cursor, user_id=user_id, item_id=item_id)
            if item["status"] != "completed":
                cursor.execute(
                    "UPDATE learning_plan_day_item SET status = 'completed', completed_at = COALESCE(completed_at, %s), updated_at = %s WHERE id = %s",
                    (now, now, item_id),
                )
            return {"item_id": int(item["id"]), "title": str(item["title"]), "status": "completed"}

    @staticmethod
    def _assert_item_unlocked(cursor: Any, *, user_id: int, item_id: int) -> None:
        """Reject completion or execution while an earlier task is unfinished."""

        cursor.execute(
            "SELECT item.id, day.id AS day_id FROM learning_plan_day_item item "
            "JOIN learning_plan_day day ON day.id = item.learning_plan_day_id "
            "JOIN learning_plan plan ON plan.id = day.plan_id "
            "WHERE item.id = %s AND plan.user_id = %s AND plan.status = 'active'",
            (item_id, user_id),
        )
        target = cursor.fetchone()
        if target is None:
            raise ValidationAppError("learning-plan item does not belong to an active user plan", details={"item_id": item_id, "user_id": user_id})
        cursor.execute(
            "SELECT previous.id, previous.title FROM learning_plan_day_item previous "
            "JOIN learning_plan_day previous_day ON previous_day.id = previous.learning_plan_day_id "
            "JOIN learning_plan_day target_day ON target_day.id = %s "
            "WHERE previous_day.plan_id = target_day.plan_id AND previous.status <> 'completed' "
            "AND (previous_day.expected_date < target_day.expected_date "
            "OR (previous_day.expected_date = target_day.expected_date AND previous.id < %s)) "
            "ORDER BY previous_day.expected_date, previous.id LIMIT 1",
            (target["day_id"], item_id),
        )
        previous = cursor.fetchone()
        if previous is not None:
            raise ValidationAppError("complete the previous learning-plan task first", details={"previous_item_id": int(previous["id"]), "previous_title": str(previous["title"]), "item_id": item_id})

    def find_reading_knowledge_point(self, *, book_id: int, item_title: str) -> dict[str, Any] | None:
        """Resolve the single knowledge point encoded in a generated reading title.

        Weekly reading tasks are produced as ``阅读：章节—知识点（15分钟）``.
        Keeping this parser here avoids selecting material from the whole book.
        """
        target = item_title.removeprefix("阅读：").rsplit("（", 1)[0].rsplit("—", 1)[-1].strip()
        if not target:
            return None
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, name, knowledge_point_code AS code, description "
                "FROM knowledge_points WHERE book_id = %s AND name = %s LIMIT 1",
                (book_id, target),
            )
            return cursor.fetchone()

    def load_replan_context(self, *, plan_id: int, diagnostic_session_id: int) -> dict[str, Any]:
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT lp.id AS plan_id, lp.user_id, lp.book_id, lp.goal_id, lp.window_start_date, lp.window_end_date, "
                "lpd.id AS day_id, lpd.expected_date FROM learning_plan lp "
                "JOIN learning_plan_day lpd ON lpd.plan_id = lp.id "
                "JOIN diagnostic_session ds ON ds.learning_plan_day_id = lpd.id "
                "WHERE lp.id = %s AND ds.id = %s AND lp.status = 'active'",
                (plan_id, diagnostic_session_id),
            )
            binding = cursor.fetchone()
            if binding is None:
                raise ValidationAppError("diagnostic session does not belong to an active plan day", details={"plan_id": plan_id, "diagnostic_session_id": diagnostic_session_id})
            cursor.execute(
                "SELECT qkp.knowledge_point_id, da.is_correct FROM diagnostic_answer da "
                "JOIN question_knowledge_points qkp ON qkp.question_id = da.question_id "
                "WHERE da.session_id = %s ORDER BY da.created_at, da.id",
                (diagnostic_session_id,),
            )
            outcomes: dict[int, list[bool]] = {}
            for row in cursor.fetchall():
                outcomes.setdefault(int(row["knowledge_point_id"]), []).append(bool(row["is_correct"]))
        context = self.load_weekly_context(user_id=int(binding["user_id"]), book_id=int(binding["book_id"]))
        if int(context["goal"]["id"]) != int(binding["goal_id"]):
            raise ValidationAppError("diagnostic session belongs to a non-active learning goal")
        return {"binding": binding, "context": context, "outcomes": outcomes}

    def update_mastery_scores(self, *, user_id: int, goal_id: int, scores: dict[int, dict[str, Any]]) -> None:
        now = datetime.now().replace(microsecond=0)
        with self.connection() as connection:
            cursor = connection.cursor()
            for point_id, value in scores.items():
                next_review_at = value.get("next_review_at")
                if isinstance(next_review_at, str):
                    next_review_at = datetime.fromisoformat(next_review_at.replace("Z", "+00:00")).replace(tzinfo=None)
                cursor.execute(
                    "UPDATE knowledge_point_master SET mastery_score = %s, confidence = %s, "
                    "next_review_at = COALESCE(%s, next_review_at), updated_at = %s "
                    "WHERE user_id = %s AND goal_id = %s AND knowledge_point_id = %s",
                    (value["mastery_score"], value["confidence"], next_review_at, now, user_id, goal_id, point_id),
                )

    def replace_future_days(self, *, plan_id: int, after_date: Any, days: list[dict[str, Any]]) -> None:
        """Keep the original seven dates; only replace unstarted items after today."""
        now = datetime.now().replace(microsecond=0)
        by_date = {str(day["date"]): day for day in days if str(day["date"]) > str(after_date)}
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT id, expected_date FROM learning_plan_day WHERE plan_id = %s AND expected_date > %s", (plan_id, after_date))
            for existing in cursor.fetchall():
                replacement = by_date.get(str(existing["expected_date"]))
                if replacement is None:
                    continue
                cursor.execute("DELETE FROM learning_plan_day_item WHERE learning_plan_day_id = %s AND status = 'todo'", (existing["id"],))
                cursor.execute("UPDATE learning_plan_day SET title = %s, adaptive_reason = %s, generated_version = generated_version + 1, priority_score = %s, updated_at = %s WHERE id = %s", (replacement["title"], replacement["adaptive_reason"], replacement["priority_score"], now, existing["id"]))
                for item in replacement["items"]:
                    cursor.execute("INSERT INTO learning_plan_day_item (learning_plan_day_id, title, description, status, source, adaptive_reason, item_type, created_at, updated_at) VALUES (%s, %s, %s, 'todo', %s, %s, 'text_learning', %s, %s)", (existing["id"], item["title"], item["description"], item["source"], item["adaptive_reason"], now, now))
            cursor.execute("UPDATE learning_plan SET adaptive_version = adaptive_version + 1, updated_at = %s WHERE id = %s", (now, plan_id))

    def replace_weekly_plan(self, *, context: dict[str, Any], days: list[dict[str, Any]]) -> int:
        """Supersede only this user's active plan for this goal, then write all layers."""
        now = datetime.now().replace(microsecond=0)
        user_id, book_id, goal_id = int(context["user_id"]), int(context["book"]["id"]), int(context["goal"]["id"])
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "UPDATE learning_plan SET status = 'superseded', updated_at = %s "
                "WHERE user_id = %s AND book_id = %s AND goal_id = %s AND status = 'active'",
                (now, user_id, book_id, goal_id),
            )
            cursor.execute(
                "INSERT INTO learning_plan (user_id, book_id, goal_id, status, window_start_date, window_end_date, daily_minutes, adaptive_version, created_at, updated_at) "
                "VALUES (%s, %s, %s, 'active', %s, %s, %s, 1, %s, %s)",
                (user_id, book_id, goal_id, days[0]["date"], days[-1]["date"], int(context["goal"]["daily_minutes"]), now, now),
            )
            plan_id = int(cursor.lastrowid)
            for day in days:
                cursor.execute(
                    "INSERT INTO learning_plan_day (plan_id, title, adaptive_reason, expected_date, generated_version, priority_score, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, 1, %s, %s, %s)",
                    (plan_id, day["title"], day["adaptive_reason"], day["date"], day["priority_score"], now, now),
                )
                day_id = int(cursor.lastrowid)
                for item in day["items"]:
                    cursor.execute(
                        "INSERT INTO learning_plan_day_item (learning_plan_day_id, title, description, status, source, adaptive_reason, item_type, created_at, updated_at) "
                        "VALUES (%s, %s, %s, 'todo', %s, %s, 'text_learning', %s, %s)",
                        (day_id, item["title"], item["description"], item["source"], item["adaptive_reason"], now, now),
                    )
        return plan_id
