"""Build a conservative per-user task-duration profile from local activity logs."""

from __future__ import annotations

from statistics import median
from typing import Any

from modules.learning_record.module import LearningRecordModule


class LearningPaceAgent:
    """Derive timing factors from completed task events; never alters user preferences."""

    BASELINE_SECONDS = {"reading": 15 * 60, "practice": 3 * 60, "review": 3 * 60, "diagnostic": 10 * 60}

    def __init__(self, learning_record: LearningRecordModule) -> None:
        self.learning_record = learning_record

    def factors(self, *, user_id: str, book_id: str) -> dict[str, float]:
        records = self.learning_record.list_activities(user_id, book_id=book_id, page=1, page_size=100)["records"]
        grouped: dict[str, list[int]] = {}
        for activity in records:
            if activity.activity_type != "task_completed":
                continue
            duration = (activity.result or {}).get("duration_seconds")
            task_type = (activity.detail or {}).get("task_type")
            if task_type not in self.BASELINE_SECONDS or not isinstance(duration, (int, float)) or duration <= 0:
                continue
            grouped.setdefault(str(task_type), []).append(int(duration))
        # Do not personalize from a single accidental short/long session.
        return {
            task_type: round(max(0.6, min(2.0, float(median(values)) / baseline)), 3)
            for task_type, baseline in self.BASELINE_SECONDS.items()
            if len(values := grouped.get(task_type, [])) >= 2
        }
