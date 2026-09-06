"""MySQL reads and writes for the seven-day learning-plan workflow."""

from __future__ import annotations

from datetime import date, datetime
import json
from typing import Any

from modules.common.errors import ValidationAppError
from modules.learner_profile.repository import MySqlLearnerProfileRepository


class MySqlLearningPlanRepository(MySqlLearnerProfileRepository):
    """Reuses the application's single MySQL configuration and transaction API."""

    @staticmethod
    def _item_type(item: dict[str, Any]) -> str:
        title = str(item.get("title") or "")
        source = str(item.get("source") or "")
        if source == "review_due" or title.startswith("学习前诊断"):
            return "diagnostic"
        if title.startswith("阅读"):
            return "reading"
        if title.startswith("复习") or source == "spaced_review":
            return "review"
        if title.startswith("练习"):
            return "practice"
        if title.startswith("编程实践"):
            return "coding"
        return "text_learning"

    def ensure_prepared_content_schema(self) -> None:
        """Add the cache columns used by plan-item pre-generation.

        The running project has historically been bootstrapped without a
        migration runner, so this idempotent compatibility migration keeps
        existing installations usable while the SQL migration is adopted.
        """
        with self.connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT COLUMN_NAME FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = 'learning_plan_day_item'"
            )
            columns = {str(row[0]) for row in cursor.fetchall()}
            definitions = {
                "prepared_status": "VARCHAR(32) NULL",
                "prepared_payload": "LONGTEXT NULL",
                "prepared_error": "TEXT NULL",
            }
            for name, definition in definitions.items():
                if name not in columns:
                    cursor.execute(f"ALTER TABLE learning_plan_day_item ADD COLUMN {name} {definition}")

    def update_goal_aim_level(self, *, user_id: int, book_id: int, aim_level: int) -> None:
        """Persist a target change before rebuilding only the unfinished work.

        The knowledge-point target scores are kept in step with the overall
        goal, so prioritisation immediately reflects the learner's new target.
        Completed plan items are deliberately not touched here.
        """
        labels = (
            "能够复述核心概念",
            "能够独立完成基础练习",
            "能够解决进阶应用问题",
            "能够指导他人 / 应对面试",
        )
        if aim_level < 0 or aim_level >= len(labels):
            raise ValidationAppError("aim_level must be between 0 and 3")
        now = datetime.now().replace(microsecond=0)
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT id FROM learning_goal WHERE user_id = %s AND book_id = %s AND status = 0 "
                "ORDER BY updated_at DESC, id DESC LIMIT 1 FOR UPDATE",
                (user_id, book_id),
            )
            goal = cursor.fetchone()
            if goal is None:
                raise ValidationAppError("an active learning goal is required", details={"user_id": user_id, "book_id": book_id})
            goal_id = int(goal["id"])
            cursor.execute(
                "UPDATE learning_goal SET goal = %s, aim_level = %s, updated_at = %s WHERE id = %s",
                (labels[aim_level], aim_level, now, goal_id),
            )
            cursor.execute(
                "UPDATE knowledge_point_master SET aim_score = %s, updated_at = %s "
                "WHERE user_id = %s AND goal_id = %s",
                (float(aim_level) / 3.0, now, user_id, goal_id),
            )

    def ensure_initial_mastery_records(self, *, user_id: int, book_id: int) -> int:
        """Backfill baseline mastery for a legacy, otherwise complete profile.

        Earlier versions could persist ``learner_profile`` and ``learning_goal``
        without creating ``knowledge_point_master`` rows.  A weekly plan needs
        those rows, but a missing row means "not assessed yet", not "profile
        does not exist".  Initialise only absent points and leave any diagnostic
        or agent-produced record untouched.
        """

        now = datetime.now().replace(microsecond=0)
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, aim_level FROM learning_goal "
                "WHERE user_id = %s AND book_id = %s AND status = 0 "
                "ORDER BY updated_at DESC, id DESC LIMIT 1",
                (user_id, book_id),
            )
            goal = cursor.fetchone()
            if goal is None:
                return 0
            aim_score = max(0.0, min(1.0, float(goal["aim_level"]) / 3.0))
            cursor.execute(
                "INSERT INTO knowledge_point_master "
                "(id, user_id, goal_id, knowledge_point_id, mastery_score, aim_score, confidence, created_at, updated_at) "
                "SELECT UUID_SHORT(), %s, %s, kp.id, 0.0, %s, 0.2, %s, %s "
                "FROM knowledge_points kp "
                "WHERE kp.book_id = %s AND NOT EXISTS ("
                "SELECT 1 FROM knowledge_point_master existing "
                "WHERE existing.user_id = %s AND existing.goal_id = %s "
                "AND existing.knowledge_point_id = kp.id)"
                ,
                (user_id, int(goal["id"]), aim_score, now, now, book_id, user_id, int(goal["id"])),
            )
            return int(cursor.rowcount)

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
            # Preferences are planning constraints, separate from the
            # knowledge-point model.  Keep them in the same context snapshot
            # so a generated plan is explainable from one set of database
            # facts.
            cursor.execute(
                "SELECT preferred_content_style, preferred_difficulty, learning_frequency, "
                "preferred_activity_types, session_duration_minutes "
                "FROM learner_profile WHERE user_id = %s ORDER BY updated_at DESC, id DESC LIMIT 1",
                (user_id,),
            )
            profile = cursor.fetchone() or {}
            activities = profile.get("preferred_activity_types") or []
            if isinstance(activities, str):
                try:
                    activities = json.loads(activities)
                except json.JSONDecodeError:
                    activities = []
            profile = {
                "content_style": str(profile.get("preferred_content_style") or "balanced"),
                "difficulty": str(profile.get("preferred_difficulty") or "adaptive"),
                "learning_frequency": str(profile.get("learning_frequency") or "flexible"),
                "activity_types": activities if isinstance(activities, list) else [],
                "session_duration_minutes": profile.get("session_duration_minutes"),
            }
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
        return {"user_id": user_id, "book": book, "goal": goal, "profile": profile, "points": points, "outcomes": outcomes, "question_ids": question_ids}

    def load_active_weekly_plan(self, *, user_id: int, book_id: int) -> dict[str, Any] | None:
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT plan.id, plan.goal_id, plan.window_start_date, plan.window_end_date, plan.daily_minutes, plan.adaptive_version, "
                "goal.goal, book.book_name "
                "FROM learning_plan plan "
                "JOIN learning_goal goal ON goal.id = plan.goal_id "
                "JOIN books book ON book.id = plan.book_id "
                "WHERE plan.user_id = %s AND plan.book_id = %s AND plan.status = 'active' "
                "ORDER BY plan.updated_at DESC, plan.id DESC LIMIT 1",
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
                    "SELECT id, title, description, status, source, adaptive_reason, item_type, started_at, completed_at, prepared_status "
                    "FROM learning_plan_day_item WHERE learning_plan_day_id = %s ORDER BY id",
                    (day["id"],),
                )
                day["items"] = list(cursor.fetchall())
            return {"plan": plan, "days": days}

    def load_current_mastery(self, *, user_id: int, book_id: int) -> list[dict[str, Any]]:
        """Read the active goal's live knowledge-point state for the dashboard.

        ``knowledge_point_master`` is updated whenever a daily diagnostic is
        confirmed.  It is therefore the source of truth for the capability
        graph; diagnostic-session summaries are only historical evidence.
        """
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT kp.id AS knowledge_point_id, kp.knowledge_point_code, kp.name, kp.description, "
                "kpm.mastery_score, kpm.aim_score, kpm.confidence "
                "FROM learning_goal goal "
                "JOIN knowledge_point_master kpm ON kpm.goal_id = goal.id AND kpm.user_id = goal.user_id "
                "JOIN knowledge_points kp ON kp.id = kpm.knowledge_point_id "
                "WHERE goal.user_id = %s AND goal.book_id = %s AND goal.status = 0 "
                "ORDER BY kp.course_order, kp.id",
                (user_id, book_id),
            )
            return list(cursor.fetchall())

    def close_overdue_items(self, *, user_id: int, book_id: int) -> int:
        """Mark unfinished tasks from prior calendar days as skipped."""
        with self.connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                "UPDATE learning_plan_day_item item "
                "JOIN learning_plan_day day ON day.id = item.learning_plan_day_id "
                "JOIN learning_plan plan ON plan.id = day.plan_id "
                "SET item.status = 'skipped', item.updated_at = NOW() "
                "WHERE plan.user_id = %s AND plan.book_id = %s AND plan.status = 'active' "
                "AND day.expected_date < CURDATE() AND item.status <> 'completed'",
                (user_id, book_id),
            )
            return int(cursor.rowcount or 0)

    def save_prepared_content(self, *, item_id: int, status: str, payload: str | None = None, error: str | None = None) -> None:
        now = datetime.now().replace(microsecond=0)
        with self.connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                "UPDATE learning_plan_day_item SET prepared_status = %s, prepared_payload = %s, prepared_error = %s, updated_at = %s WHERE id = %s",
                (status, payload, error, now, item_id),
            )

    def load_plan_items(self, *, plan_id: int) -> list[dict[str, Any]]:
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT item.id, item.title, item.description, item.source, item.item_type, day.expected_date "
                "FROM learning_plan_day_item item JOIN learning_plan_day day ON day.id = item.learning_plan_day_id "
                "WHERE day.plan_id = %s ORDER BY day.expected_date, item.id",
                (plan_id,),
            )
            return list(cursor.fetchall())

    def load_plan_item_title(self, *, item_id: int) -> str | None:
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT title FROM learning_plan_day_item WHERE id = %s", (item_id,))
            row = cursor.fetchone()
        return str(row["title"]) if row and row.get("title") else None

    def load_prepared_content(self, *, item_id: int) -> dict[str, Any] | None:
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT prepared_status, prepared_payload, prepared_error FROM learning_plan_day_item WHERE id = %s", (item_id,))
            row = cursor.fetchone()
        if not row or not row.get("prepared_payload"):
            return None
        import json
        try:
            return json.loads(row["prepared_payload"])
        except (TypeError, ValueError):
            return None

    def get_prepared_content_status(self, *, item_id: int) -> str | None:
        """Return preparation state without loading the potentially large payload."""
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT prepared_status FROM learning_plan_day_item WHERE id = %s", (item_id,))
            row = cursor.fetchone()
        return str(row["prepared_status"]) if row and row.get("prepared_status") else None

    def find_prepared_reading(self, *, book_id: int, item_title: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT item.id, item.prepared_payload FROM learning_plan_day_item item "
                "JOIN learning_plan_day day ON day.id = item.learning_plan_day_id "
                "JOIN learning_plan plan ON plan.id = day.plan_id "
                "WHERE plan.book_id = %s AND plan.status = 'active' AND item.title = %s "
                "AND item.source = 'weak_point' ORDER BY item.id DESC LIMIT 1",
                (book_id, item_title),
            )
            row = cursor.fetchone()
        if not row or not row.get("prepared_payload"):
            return None
        import json
        try:
            return json.loads(row["prepared_payload"])
        except (TypeError, ValueError):
            return None

    def load_plan_day(self, *, user_id: int, book_id: int, expected_date: Any) -> dict[str, Any] | None:
        """Read one active-plan day and its concrete tasks."""

        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT day.id, day.plan_id, day.title, day.expected_date "
                "FROM learning_plan_day day JOIN learning_plan plan ON plan.id = day.plan_id "
                "WHERE plan.user_id = %s AND plan.book_id = %s AND plan.status = 'active' "
                "AND day.expected_date = %s LIMIT 1",
                (user_id, book_id, expected_date),
            )
            day = cursor.fetchone()
            if day is None:
                return None
            cursor.execute(
                "SELECT id, title, description, status, source, adaptive_reason, item_type "
                "FROM learning_plan_day_item WHERE learning_plan_day_id = %s ORDER BY id",
                (day["id"],),
            )
            day["items"] = list(cursor.fetchall())
            return day

    def append_day_items(self, *, day_id: int, items: list[dict[str, Any]]) -> None:
        """Append one dynamically generated batch, preserving completed work."""

        if not items:
            return
        now = datetime.now().replace(microsecond=0)
        with self.connection() as connection:
            cursor = connection.cursor()
            for item in items:
                cursor.execute(
                    "INSERT INTO learning_plan_day_item "
                    "(learning_plan_day_id, title, description, status, source, adaptive_reason, item_type, created_at, updated_at) "
                    "VALUES (%s, %s, %s, 'todo', %s, %s, %s, %s, %s)",
                    (
                        day_id,
                        item["title"],
                        item["description"],
                        item["source"],
                        item["adaptive_reason"],
                        self._item_type(item),
                        now,
                        now,
                    ),
                )

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
                    # 任务可能由阅读弹窗直接完成，未必先写入 started_at；
                    # 补齐开始时间和完成时间，保证 MySQL 中有完整时间链路。
                    "UPDATE learning_plan_day_item SET status = 'completed', started_at = COALESCE(started_at, %s), completed_at = COALESCE(completed_at, %s), updated_at = %s WHERE id = %s",
                    (now, now, now, item_id),
                )
                cursor.execute(
                    "UPDATE learning_plan_day_item SET started_at = COALESCE(started_at, %s) WHERE id = %s",
                    (now, item_id),
                )
            cursor.execute("SELECT learning_plan_day_id, started_at FROM learning_plan_day_item WHERE id = %s", (item_id,))
            day_ref = cursor.fetchone()
            if day_ref and day_ref.get("learning_plan_day_id"):
                day_id = int(day_ref["learning_plan_day_id"])
                cursor.execute("UPDATE learning_plan_day SET started_at = COALESCE(started_at, %s), updated_at = %s WHERE id = %s", (day_ref.get("started_at") or now, now, day_id))
                cursor.execute("SELECT COUNT(*) AS pending FROM learning_plan_day_item WHERE learning_plan_day_id = %s AND status NOT IN ('completed','skipped','rescheduled')", (day_id,))
                if int(cursor.fetchone()["pending"] or 0) == 0:
                    cursor.execute("UPDATE learning_plan_day SET completed_at = COALESCE(completed_at, %s), updated_at = %s WHERE id = %s", (now, now, day_id))
            return {"item_id": int(item["id"]), "title": str(item["title"]), "status": "completed"}

    def start_weekly_plan_item(self, *, user_id: int, item_id: int) -> dict[str, Any]:
        """Persist the moment a learner starts a plan item."""
        now = datetime.now().replace(microsecond=0)
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT item.id, item.title, item.status, item.learning_plan_day_id FROM learning_plan_day_item item "
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
                cursor.execute(
                    "UPDATE learning_plan_day_item SET status = 'in_progress', started_at = COALESCE(started_at, %s), updated_at = %s WHERE id = %s",
                    (now, now, item_id),
                )
                cursor.execute(
                    "UPDATE learning_plan_day SET started_at = COALESCE(started_at, %s), updated_at = %s WHERE id = %s",
                    (now, now, int(item["learning_plan_day_id"])),
                )
            return {"item_id": int(item["id"]), "title": str(item["title"]), "status": "completed" if item["status"] == "completed" else "in_progress"}

    def plan_requires_rollover(self, *, user_id: int, item_id: int) -> bool:
        """Whether completing this item finished (or expired) the active 7-day window."""
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT plan.id, plan.window_end_date, "
                "SUM(CASE WHEN item.status NOT IN ('completed', 'skipped', 'rescheduled') THEN 1 ELSE 0 END) AS pending "
                "FROM learning_plan plan JOIN learning_plan_day day ON day.plan_id = plan.id "
                "JOIN learning_plan_day_item item ON item.learning_plan_day_id = day.id "
                "JOIN learning_plan_day_item target ON target.id = %s "
                "JOIN learning_plan_day target_day ON target_day.id = target.learning_plan_day_id AND target_day.plan_id = plan.id "
                "WHERE plan.user_id = %s AND plan.status = 'active' "
                "GROUP BY plan.id, plan.window_end_date",
                (item_id, user_id),
            )
            row = cursor.fetchone()
        if not row:
            return False
        end_date = row.get("window_end_date")
        if hasattr(end_date, "date"):
            end_date = end_date.date()
        try:
            expired = end_date is not None and end_date < date.today()
        except TypeError:
            expired = False
        return bool(expired or int(row.get("pending") or 0) == 0)

    def load_item_context(self, *, user_id: int, item_id: int) -> dict[str, Any] | None:
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT plan.book_id FROM learning_plan_day_item item "
                "JOIN learning_plan_day day ON day.id = item.learning_plan_day_id "
                "JOIN learning_plan plan ON plan.id = day.plan_id "
                "WHERE item.id = %s AND plan.user_id = %s AND plan.status = 'active' LIMIT 1",
                (item_id, user_id),
            )
            return cursor.fetchone()

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
        # A new calendar day starts a new learning session. Close unfinished
        # items from earlier days so they no longer block today's diagnosis.
        cursor.execute(
            "UPDATE learning_plan_day_item previous "
            "JOIN learning_plan_day previous_day ON previous_day.id = previous.learning_plan_day_id "
            "JOIN learning_plan_day target_day ON target_day.id = %s "
            "SET previous.status = 'skipped', previous.updated_at = NOW() "
                "WHERE previous_day.plan_id = target_day.plan_id AND previous.status NOT IN ('completed', 'skipped', 'rescheduled') "
            "AND previous_day.expected_date < CURDATE() AND previous_day.expected_date < target_day.expected_date",
            (target["day_id"],),
        )
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
                "SELECT id, name, knowledge_point_code AS code, description, course_order "
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
        """Keep future day outlines; never pre-write their concrete tasks."""
        now = datetime.now().replace(microsecond=0)
        by_date = {str(day["date"]): day for day in days if str(day["date"]) > str(after_date)}
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT id, expected_date FROM learning_plan_day WHERE plan_id = %s AND expected_date > %s", (plan_id, after_date))
            for existing in cursor.fetchall():
                replacement = by_date.get(str(existing["expected_date"]))
                if replacement is None:
                    continue
                # A previously generated legacy plan may still have future
                # items.  They are invalid once mastery changed, whereas
                # completed evidence is retained for audit/history.
                cursor.execute("DELETE FROM learning_plan_day_item WHERE learning_plan_day_id = %s AND status = 'todo'", (existing["id"],))
                cursor.execute("UPDATE learning_plan_day SET title = %s, adaptive_reason = %s, generated_version = generated_version + 1, priority_score = %s, updated_at = %s WHERE id = %s", (replacement["title"], replacement["adaptive_reason"], replacement["priority_score"], now, existing["id"]))
                for item in replacement["items"]:
                    cursor.execute("INSERT INTO learning_plan_day_item (learning_plan_day_id, title, description, status, source, adaptive_reason, item_type, created_at, updated_at) VALUES (%s, %s, %s, 'todo', %s, %s, %s, %s, %s)", (existing["id"], item["title"], item["description"], item["source"], item["adaptive_reason"], self._item_type(item), now, now))
            cursor.execute("UPDATE learning_plan SET adaptive_version = adaptive_version + 1, updated_at = %s WHERE id = %s", (now, plan_id))

    def replace_weekly_plan(self, *, context: dict[str, Any], days: list[dict[str, Any]]) -> int:
        """Correct only unfinished items in the current active weekly plan.

        A replan must not turn completed work into a new copy or move it into a
        replacement plan.  It therefore keeps the current plan and its
        completed rows in place, replacing only ``todo``/``in_progress``/
        ``skipped`` rows for dates in the regenerated window.
        """
        now = datetime.now().replace(microsecond=0)
        user_id, book_id, goal_id = int(context["user_id"]), int(context["book"]["id"]), int(context["goal"]["id"])
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, window_start_date FROM learning_plan "
                "WHERE user_id = %s AND book_id = %s AND status = 'active' "
                "ORDER BY updated_at DESC, id DESC LIMIT 1 FOR UPDATE",
                (user_id, book_id),
            )
            active_plan = cursor.fetchone()
            if active_plan is None:
                cursor.execute(
                    "INSERT INTO learning_plan (user_id, book_id, goal_id, status, window_start_date, window_end_date, daily_minutes, adaptive_version, created_at, updated_at) "
                    "VALUES (%s, %s, %s, 'active', %s, %s, %s, 1, %s, %s)",
                    (user_id, book_id, goal_id, days[0]["date"], days[-1]["date"], int(context["goal"]["daily_minutes"]), now, now),
                )
                plan_id = int(cursor.lastrowid)
            else:
                plan_id = int(active_plan["id"])
                cursor.execute(
                    "UPDATE learning_plan SET goal_id = %s, window_end_date = %s, daily_minutes = %s, "
                    "adaptive_version = adaptive_version + 1, updated_at = %s WHERE id = %s",
                    (goal_id, days[-1]["date"], int(context["goal"]["daily_minutes"]), now, plan_id),
                )
            for day in days:
                cursor.execute(
                    "SELECT id FROM learning_plan_day WHERE plan_id = %s AND expected_date = %s "
                    "ORDER BY id LIMIT 1 FOR UPDATE",
                    (plan_id, day["date"]),
                )
                existing_day = cursor.fetchone()
                if existing_day is None:
                    cursor.execute(
                        "INSERT INTO learning_plan_day (plan_id, title, adaptive_reason, expected_date, generated_version, priority_score, created_at, updated_at) "
                        "VALUES (%s, %s, %s, %s, 1, %s, %s, %s)",
                        (plan_id, day["title"], day["adaptive_reason"], day["date"], day["priority_score"], now, now),
                    )
                    day_id = int(cursor.lastrowid)
                    completed_titles: set[str] = set()
                    unfinished_count = 1
                else:
                    day_id = int(existing_day["id"])
                    cursor.execute(
                        "SELECT title, status FROM learning_plan_day_item WHERE learning_plan_day_id = %s FOR UPDATE",
                        (day_id,),
                    )
                    existing_items = cursor.fetchall()
                    completed_titles = {str(item["title"]) for item in existing_items if item["status"] == "completed"}
                    unfinished_count = sum(1 for item in existing_items if item["status"] != "completed")

                    # A day that has already been fully finished is historical
                    # evidence, not a source of extra replacement tasks.
                    if completed_titles and unfinished_count == 0:
                        continue

                    cursor.execute(
                        "DELETE FROM learning_plan_day_item WHERE learning_plan_day_id = %s AND status <> 'completed'",
                        (day_id,),
                    )
                    cursor.execute(
                        "UPDATE learning_plan_day SET title = %s, adaptive_reason = %s, generated_version = generated_version + 1, "
                        "priority_score = %s, updated_at = %s WHERE id = %s",
                        (day["title"], day["adaptive_reason"], day["priority_score"], now, day_id),
                    )

                # Do not insert a fresh pending duplicate for an item the
                # learner has already completed on this date.
                for item in (item for item in day["items"] if str(item["title"]) not in completed_titles):
                    cursor.execute(
                        "INSERT INTO learning_plan_day_item (learning_plan_day_id, title, description, status, source, adaptive_reason, item_type, created_at, updated_at) "
                        "VALUES (%s, %s, %s, 'todo', %s, %s, %s, %s, %s)",
                        (day_id, item["title"], item["description"], item["source"], item["adaptive_reason"], self._item_type(item), now, now),
                    )
        return plan_id
