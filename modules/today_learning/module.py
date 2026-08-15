"""今日学习页面的聚合服务。"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from modules.common.errors import ResourceNotFoundError
from modules.diagnosis.workflow import DiagnosisWorkflow
from modules.learning_plan.module import LearningPlanModule
from modules.learning_record.models import LearningActivity
from modules.learning_record.module import LearningRecordModule

from .field_rules import validate_query
from .models import TodayLearning, WeeklyProgress


BOOKS = {
    "ml": {"id": "ml", "title": "《机器学习》", "shortTitle": "机器学习", "subtitle": "监督学习与模型评估"},
    "dl": {"id": "dl", "title": "《深度学习》", "shortTitle": "深度学习", "subtitle": "神经网络、训练与泛化"},
}
RECORD_BOOK_IDS = {"ml": "ml-001", "dl": "dl-001"}
KNOWLEDGE_POINT_LABELS = {
    "supervised_learning": "监督学习",
    "linear_regression": "线性回归",
    "model_evaluation": "模型评估",
    "overfitting": "偏差与方差",
    "deep_learning": "深度学习基础",
    "neural_network": "神经网络",
    "backpropagation": "反向传播",
    "convolution": "卷积网络",
}


class TodayLearningModule:
    def __init__(self, learning_plan: LearningPlanModule, learning_record: LearningRecordModule, diagnosis: DiagnosisWorkflow) -> None:
        self.learning_plan = learning_plan
        self.learning_record = learning_record
        self.diagnosis = diagnosis

    def get_today_learning(self, *, user_id: str, book_id: str) -> dict[str, Any]:
        values = validate_query(user_id, book_id)
        book = BOOKS.get(values["book_id"], {"id": values["book_id"], "title": values["book_id"], "shortTitle": values["book_id"], "subtitle": ""})
        plan = self.learning_plan.get_saved(book_id=values["book_id"])
        activities = [
            activity
            for activity in self.learning_record.list_activities(values["user_id"], page=1, page_size=100)["records"]
            if activity.book_id in {values["book_id"], RECORD_BOOK_IDS.get(values["book_id"], values["book_id"])}
        ]
        tasks = self._tasks(plan)
        goal = str((plan or {}).get("goal") or self._latest_goal(activities) or "")
        graph = self._knowledge_graph(activities, goal, tasks)
        progress = self._weekly_progress(activities, tasks)
        recommendation = self._recommendation(tasks, graph)
        continue_learning = self._continue_learning(tasks)
        completed = sum(task.get("status") == "completed" for task in tasks)
        result = TodayLearning(
            book=book,
            goal=goal,
            last_learned=self._last_learned(activities),
            weekly_progress=progress,
            recommendation=recommendation,
            knowledge_graph=graph,
            tasks=tasks,
        )
        payload = {
            "book": result.book,
            "goal": result.goal,
            "lastLearned": result.last_learned,
            "weeklyProgress": {
                "progressPercent": result.weekly_progress.progress_percent,
                "completedTaskCount": result.weekly_progress.completed_task_count,
                "totalTaskCount": result.weekly_progress.total_task_count,
                "studyDurationSeconds": result.weekly_progress.study_duration_seconds,
                "studyDurationHours": round(result.weekly_progress.study_duration_seconds / 3600, 2),
                "accuracy": result.weekly_progress.accuracy,
                "dailyDuration": result.weekly_progress.daily_duration,
            },
            "recommendation": result.recommendation or None,
            "knowledgeGraph": result.knowledge_graph,
            "tasks": result.tasks,
            "taskSummary": {"completed": completed, "total": len(tasks)},
            "continueLearning": continue_learning,
        }
        return payload

    @staticmethod
    def _tasks(plan: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not plan:
            return []
        today = date.today().isoformat()
        result = []
        for task in plan.get("tasks") or []:
            expected_date = task.get("expected_completion_date") or task.get("expectedCompletionDate")
            if expected_date and expected_date != today:
                continue
            normalized = dict(task)
            normalized.setdefault("expected_completion_date", expected_date or today)
            result.append(normalized)
        return result

    @staticmethod
    def _latest_goal(activities: list[LearningActivity]) -> str:
        for activity in activities:
            if activity.category == "diagnostic":
                prefix = activity.description.split(" 路 ", 1)[0]
                return prefix
        return ""

    @staticmethod
    def _last_learned(activities: list[LearningActivity]) -> str:
        for activity in activities:
            if activity.category == "task":
                return activity.detail.get("task_title") or activity.title
        return ""

    @staticmethod
    def _knowledge_graph(activities: list[LearningActivity], goal: str, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        latest = next((item for item in activities if item.category == "diagnostic" and item.result.get("knowledge_point_results")), None)
        task_by_knowledge_point = {
            point_id: task
            for task in tasks
            for point_id in task.get("knowledge_point_ids", task.get("knowledgePointIds", []))
        }
        nodes = []
        for item in (latest.result.get("knowledge_point_results", []) if latest else []):
            total = int(item.get("total", 0))
            correct = int(item.get("correct", 0))
            score = correct / total if total else None
            raw_status = item.get("calibrated_status") or item.get("ai_status") or ""
            status = "weak" if raw_status in {"不会", "基本了解"} else "good" if raw_status == "掌握" else "learning"
            knowledge_point_id = item.get("knowledge_point_id", "")
            task = task_by_knowledge_point.get(knowledge_point_id) or next((candidate for candidate in tasks if str(candidate.get("id", "")).endswith(f"-{knowledge_point_id}")), {})
            nodes.append({"id": knowledge_point_id, "label": KNOWLEDGE_POINT_LABELS.get(knowledge_point_id, knowledge_point_id), "status": status, "accuracy": round(score * 100, 2) if score is not None else None, "masteryScore": score, "taskId": task.get("id"), "reason": task.get("reason", ""), "description": task.get("description", "")})
        return {"goal": goal, "nodes": nodes}

    @staticmethod
    def _weekly_progress(activities: list[LearningActivity], tasks: list[dict[str, Any]]) -> WeeklyProgress:
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=now.weekday())
        weekly = []
        daily: dict[str, int] = {}
        correct = total = 0
        for activity in activities:
            try:
                occurred = datetime.fromisoformat(activity.occurred_at.replace("Z", "+00:00"))
            except ValueError:
                continue
            if occurred < start:
                continue
            weekly.append(activity)
            seconds = int(activity.result.get("duration_seconds", activity.result.get("durationSeconds", 0)) or 0)
            key = occurred.date().isoformat()
            daily[key] = daily.get(key, 0) + seconds
            correct += int(activity.result.get("correct_count", activity.result.get("correctCount", 0)) or 0)
            total += int(activity.result.get("total_count", activity.result.get("totalCount", 0)) or 0)
        completed = sum(task.get("status") == "completed" for task in tasks)
        total_tasks = len(tasks)
        return WeeklyProgress(
            progress_percent=round(completed / total_tasks * 100, 2) if total_tasks else 0,
            completed_task_count=completed,
            total_task_count=total_tasks,
            study_duration_seconds=sum(daily.values()),
            accuracy=round(correct / total * 100, 2) if total else 0,
            daily_duration=[{"date": day, "durationSeconds": seconds} for day, seconds in sorted(daily.items())],
        )

    @staticmethod
    def _recommendation(tasks: list[dict[str, Any]], graph: dict[str, Any]) -> dict[str, Any] | None:
        task = next((item for item in tasks if item.get("status") != "completed"), None)
        if not task:
            return None
        return {"taskId": task.get("id", ""), "title": task.get("title", ""), "minutes": task.get("minutes", 0), "difficulty": task.get("difficulty", ""), "reason": task.get("reason", ""), "priority": "highest"}

    @staticmethod
    def _continue_learning(tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
        task = next((item for item in tasks if item.get("status") == "in_progress"), None)
        task = task or next((item for item in tasks if item.get("status") == "todo"), None)
        if not task:
            return None
        return {
            "taskId": task.get("id", ""),
            "title": task.get("title", ""),
            "type": task.get("type", ""),
            "minutes": task.get("minutes", 0),
            "status": task.get("status", "todo"),
            "expectedCompletionDate": task.get("expected_completion_date") or task.get("expectedCompletionDate", ""),
            "description": task.get("description", ""),
            "reason": task.get("reason", ""),
        }
