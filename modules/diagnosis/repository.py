"""Persist daily diagnostic sessions and answers in MySQL."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from modules.common.errors import ValidationAppError
from modules.learning_plan.repository import MySqlLearningPlanRepository


class MySqlDiagnosisRepository(MySqlLearningPlanRepository):
    def load_knowledge_point_states(self, *, user_id: int, book_id: int) -> dict[str, dict[str, Any]]:
        """Return the MySQL learner model used for diagnostic planning and updates."""

        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT id FROM learning_goal WHERE user_id = %s AND book_id = %s AND status = 0 "
                "ORDER BY updated_at DESC, id DESC LIMIT 1",
                (user_id, book_id),
            )
            goal = cursor.fetchone()
            if goal is None:
                return {}
            cursor.execute(
                "SELECT kp.knowledge_point_code, kpm.mastery_score, kpm.confidence, kpm.next_review_at "
                "FROM knowledge_point_master kpm "
                "JOIN knowledge_points kp ON kp.id = kpm.knowledge_point_id "
                "WHERE kpm.user_id = %s AND kpm.goal_id = %s",
                (user_id, goal["id"]),
            )
            return {
                str(row["knowledge_point_code"]): {
                    "masteryScore": float(row.get("mastery_score") or 0.0),
                    "confidence": float(row.get("confidence") or 0.0),
                    "nextReviewAt": row.get("next_review_at").isoformat()
                    if row.get("next_review_at") is not None
                    else None,
                }
                for row in cursor.fetchall()
            }

    def start_daily_session(self, *, user_id: int, learning_plan_day_id: int, learning_plan_item_id: int | None = None) -> dict[str, int]:
        now = datetime.now().replace(microsecond=0)
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT lp.id AS plan_id, lp.book_id, lp.goal_id FROM learning_plan_day d "
                "JOIN learning_plan lp ON lp.id = d.plan_id WHERE d.id = %s AND lp.user_id = %s AND lp.status = 'active'",
                (learning_plan_day_id, user_id),
            )
            binding = cursor.fetchone()
            if binding is None:
                raise ValidationAppError("learningPlanDayId does not belong to an active user plan")
            item_id = learning_plan_item_id
            if item_id is not None:
                cursor.execute(
                    "SELECT item.id FROM learning_plan_day_item item "
                    "WHERE item.id = %s AND item.learning_plan_day_id = %s",
                    (item_id, learning_plan_day_id),
                )
                if cursor.fetchone() is None:
                    raise ValidationAppError("learningPlanItemId does not belong to learningPlanDayId")
                self._assert_item_unlocked(cursor, user_id=user_id, item_id=item_id)
            cursor.execute(
                "INSERT INTO diagnostic_session (user_id, book_id, goal_id, session_type, learning_plan_day_id, total_questions, correct_count, created_at, updated_at) VALUES (%s, %s, %s, 1, %s, 0, 0, %s, %s)",
                (user_id, binding["book_id"], binding["goal_id"], learning_plan_day_id, now, now),
            )
            result = {"plan_id": int(binding["plan_id"]), "session_id": int(cursor.lastrowid)}
            if item_id is not None:
                result["item_id"] = int(item_id)
            return result

    @staticmethod
    def _assert_item_unlocked(cursor: Any, *, user_id: int, item_id: int) -> None:
        cursor.execute(
            "SELECT item.id, day.id AS day_id, day.expected_date FROM learning_plan_day_item item "
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

    def save_answers(self, *, session_id: int, records: list[Any]) -> None:
        now = datetime.now().replace(microsecond=0)
        item_ids = [str(record.question.id) for record in records]
        if not item_ids:
            return
        placeholders = ", ".join(["%s"] * len(item_ids))
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT book_id FROM diagnostic_session WHERE id = %s", (session_id,))
            session = cursor.fetchone()
            if session is None:
                raise ValidationAppError("diagnostic session does not exist")
            cursor.execute(f"SELECT id, learning_item_id FROM questions WHERE book_id = %s AND learning_item_id IN ({placeholders})", (session["book_id"], *item_ids))
            question_ids = {str(row["learning_item_id"]): int(row["id"]) for row in cursor.fetchall()}
            saved = correct = 0
            for record in records:
                question_id = question_ids.get(str(record.question.id))
                if question_id is None:
                    continue
                cursor.execute("INSERT INTO diagnostic_answer (session_id, question_id, submitted_answer, correct_answer, is_correct, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s)", (session_id, question_id, record.submitted_answer, record.correct_answer, int(record.is_correct), now, now))
                saved += 1
                correct += int(record.is_correct)
            if saved != len(records):
                raise ValidationAppError("some diagnostic questions are not mapped in MySQL", details={"saved": saved, "expected": len(records)})
            cursor.execute("UPDATE diagnostic_session SET total_questions = %s, correct_count = %s, updated_at = %s WHERE id = %s", (saved, correct, now, session_id))

    def complete_daily_diagnostic_task(self, *, session_id: int) -> None:
        """Mark the plan's daily-diagnosis item complete after its answers are confirmed.

        The session is bound to exactly one learning-plan day, so this update never
        changes a reading or exercise task from another day.
        """
        now = datetime.now().replace(microsecond=0)
        with self.connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                "UPDATE learning_plan_day_item item "
                "JOIN diagnostic_session session ON session.learning_plan_day_id = item.learning_plan_day_id "
                "SET item.status = 'completed', item.completed_at = COALESCE(item.completed_at, %s), item.updated_at = %s "
                "WHERE session.id = %s AND item.source = 'review_due' "
                "AND item.status IN ('todo', 'in_progress')",
                (now, now, session_id),
            )
