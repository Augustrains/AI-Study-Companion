"""MySQL-backed learning timeline assembled from the application's source tables."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

from modules.learner_profile.repository import MySqlLearnerProfileRepository

from .models import LearningActivity


class MySqlLearningRecordRepository(MySqlLearnerProfileRepository):
    """Read learning history from persisted task, diagnosis, QA and profile data.

    The application deliberately does not maintain a second mutable "activity"
    table.  The timeline is derived from the business records that actually
    happened, which keeps it accurate even after a server restart.
    """

    def list_activities(self, *, user_id: str, category: str | None = None, start_date: date | None = None, end_date: date | None = None) -> list[LearningActivity]:
        user_key = int(user_id)
        activities: list[LearningActivity] = []
        with self.connection() as connection:
            cursor = connection.cursor(dictionary=True)
            if category in {None, "task"}:
                cursor.execute(
                    "SELECT item.id, item.title, item.description, item.status, item.item_type, item.started_at, item.completed_at, "
                    "plan.book_id FROM learning_plan_day_item item "
                    "JOIN learning_plan_day day ON day.id = item.learning_plan_day_id "
                    "JOIN learning_plan plan ON plan.id = day.plan_id "
                    "WHERE plan.user_id = %s AND item.status IN ('in_progress', 'completed') "
                    "AND COALESCE(item.completed_at, item.started_at) IS NOT NULL",
                    (user_key,),
                )
                activities.extend(self._task_activity(row, user_key) for row in cursor.fetchall())
            if category in {None, "diagnostic"}:
                cursor.execute(
                    "SELECT id, book_id, total_questions, correct_count, created_at, updated_at "
                    "FROM diagnostic_session WHERE user_id = %s AND total_questions > 0",
                    (user_key,),
                )
                activities.extend(self._diagnostic_activity(row, user_key) for row in cursor.fetchall())
            if category in {None, "qa"}:
                cursor.execute(
                    "SELECT id, book_id, content, created_at FROM consultation_messages "
                    "WHERE user_id = %s AND role = 'user' AND is_context_reset = 0",
                    (user_key,),
                )
                activities.extend(self._qa_activity(row, user_key) for row in cursor.fetchall())
            if category in {None, "profile"}:
                cursor.execute(
                    "SELECT id, created_at, updated_at FROM learner_profile WHERE user_id = %s",
                    (user_key,),
                )
                activities.extend(self._profile_activity(row, user_key) for row in cursor.fetchall())

        filtered = [item for item in activities if self._within_range(item.occurred_at, start_date, end_date)]
        return sorted(filtered, key=lambda item: item.occurred_at, reverse=True)

    def overview(self, *, user_id: str, start_date: date, end_date: date) -> dict[str, Any]:
        """Return user-facing recap metrics and 35-day activity calendar."""

        all_activities = self.list_activities(user_id=user_id, start_date=start_date, end_date=end_date)
        today = date.today().isoformat()
        today_rows = [item for item in all_activities if item.occurred_at[:10] == today]
        completed = [item for item in today_rows if item.activity_type == "task_completed"]
        diagnostic = [item for item in today_rows if item.activity_type == "diagnostic_completed"]
        duration_seconds = sum(int(item.result.get("duration_seconds") or 0) for item in completed)
        correct = sum(int(item.result.get("correct_count") or 0) for item in diagnostic)
        questions = sum(int(item.result.get("total_count") or 0) for item in diagnostic)

        activity_by_day: dict[str, list[LearningActivity]] = defaultdict(list)
        today_date = date.today()
        calendar_start = today_date.replace(day=1)
        next_month = date(today_date.year + (today_date.month == 12), 1 if today_date.month == 12 else today_date.month + 1, 1)
        calendar_end = date.fromordinal(next_month.toordinal() - 1)
        calendar_activities = self.list_activities(user_id=user_id, start_date=calendar_start, end_date=calendar_end)
        for item in calendar_activities:
            activity_by_day[item.occurred_at[:10]].append(item)
        calendar = []
        for offset in range(calendar_end.day):
            day = date.fromordinal(calendar_start.toordinal() + offset).isoformat()
            rows = activity_by_day.get(day, [])
            calendar.append({
                "date": day,
                "activityCount": len(rows),
                "completedTasks": sum(item.activity_type == "task_completed" for item in rows),
                "studyMinutes": round(sum(int(item.result.get("duration_seconds") or 0) for item in rows if item.activity_type == "task_completed") / 60),
            })
        return {
            "today": {
                "activityCount": len(today_rows),
                "completedTasks": len(completed),
                "studyMinutes": round(duration_seconds / 60),
                "diagnosticAccuracy": round(correct / questions * 100) if questions else None,
            },
            "calendar": calendar,
        }

    @staticmethod
    def _timestamp(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _within_range(occurred_at: str, start_date: date | None, end_date: date | None) -> bool:
        try:
            occurred = datetime.fromisoformat(occurred_at.replace("Z", "+00:00")).date()
        except ValueError:
            return False
        return (start_date is None or occurred >= start_date) and (end_date is None or occurred <= end_date)

    def _task_activity(self, row: dict[str, Any], user_id: int) -> LearningActivity:
        completed = row["status"] == "completed"
        occurred = row["completed_at"] if completed else row["started_at"]
        duration = 0
        if completed and row.get("started_at") and row.get("completed_at"):
            duration = max(0, int((row["completed_at"] - row["started_at"]).total_seconds()))
        return LearningActivity(
            id=f"task-{row['id']}-{self._timestamp(occurred)}", user_id=str(user_id), category="task",
            activity_type="task_completed" if completed else "task_started", status="success" if completed else "in_progress",
            title="完成学习任务" if completed else "开始学习任务",
            description=f"{row['title']} · {row.get('description') or row.get('item_type') or '学习任务'}",
            occurred_at=self._timestamp(occurred), created_at=self._timestamp(occurred), updated_at=self._timestamp(occurred),
            book_id=str(row.get("book_id") or ""), task_id=str(row["id"]), result={"duration_seconds": duration},
        )

    def _diagnostic_activity(self, row: dict[str, Any], user_id: int) -> LearningActivity:
        return LearningActivity(
            id=f"diagnostic-{row['id']}", user_id=str(user_id), category="diagnostic", activity_type="diagnostic_completed", status="success",
            title="完成能力诊断", description=f"正确 {row['correct_count']}/{row['total_questions']}",
            occurred_at=self._timestamp(row["updated_at"]), created_at=self._timestamp(row["created_at"]), updated_at=self._timestamp(row["updated_at"]),
            book_id=str(row.get("book_id") or ""), result={"correct_count": row["correct_count"], "total_count": row["total_questions"], "accuracy": round(row["correct_count"] / row["total_questions"], 4)},
        )

    def _qa_activity(self, row: dict[str, Any], user_id: int) -> LearningActivity:
        text = " ".join(str(row.get("content") or "").split())
        excerpt = text[:80] + ("…" if len(text) > 80 else "")
        occurred = self._timestamp(row["created_at"])
        return LearningActivity(id=f"qa-{row['id']}", user_id=str(user_id), category="qa", activity_type="qa_asked", status="success", title="资料问答", description=excerpt or "围绕学习资料进行提问", occurred_at=occurred, created_at=occurred, updated_at=occurred, book_id=str(row.get("book_id") or ""))

    def _profile_activity(self, row: dict[str, Any], user_id: int) -> LearningActivity:
        created = self._timestamp(row["created_at"])
        updated = self._timestamp(row["updated_at"])
        changed = created != updated
        return LearningActivity(id=f"profile-{row['id']}-{updated}", user_id=str(user_id), category="profile", activity_type="profile_updated" if changed else "profile_created", status="success", title="更新学习画像" if changed else "建立学习画像", description="已保存学习背景、偏好与目标说明", occurred_at=updated, created_at=created, updated_at=updated)
