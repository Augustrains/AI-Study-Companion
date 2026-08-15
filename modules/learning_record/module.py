"""学习记录查询模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from modules.common import api as common_api

from .field_rules import validate_learning_activity
from .models import LearningActivity


class LearningRecordModule:
    """从 data 下的活动 JSON 读取并整理最近活动。"""

    DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "learning_record" / "activities.json"

    def __init__(
        self,
        reader: common_api.json_storage.JsonContentReader | None = None,
        store: common_api.json_storage.JsonStore | None = None,
        path: str | Path | None = None,
    ) -> None:
        target = Path(path) if path is not None else Path(reader.path) if reader is not None else self.DEFAULT_PATH
        self.reader = reader or common_api.json_storage.JsonContentReader(target)
        self.store = store or common_api.json_storage.JsonStore()

    def list_activities(
        self,
        user_id: str,
        *,
        category: str | None = None,
        activity_type: str | None = None,
        status: str | None = None,
        book_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, object]:
        """查询指定用户的活动，缺少活动文件时按空列表处理。"""

        activities = [
            activity
            for activity in self._read_activities()
            if activity.user_id == user_id
            and (category is None or activity.category == category)
            and (activity_type is None or activity.activity_type == activity_type)
            and (status is None or activity.status == status)
            and (book_id is None or activity.book_id == book_id)
        ]
        activities.sort(key=lambda item: item.occurred_at, reverse=True)

        total = len(activities)
        start = (page - 1) * page_size
        end = start + page_size
        records = activities[start:end]
        return {
            "records": records,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": end < total,
        }

    def get_activity(self, user_id: str, activity_id: str) -> LearningActivity | None:
        for activity in self._read_activities():
            if activity.user_id == user_id and activity.id == activity_id:
                return activity
        return None

    def record_completed_diagnosis(self, diagnosis: Any) -> LearningActivity:
        """写入一次已完成诊断活动，并使用确定性 ID 避免重复写入。"""

        activity_id = f"activity_diagnostic_completed_{diagnosis.diagnosis_id}"
        existing = self.get_activity(diagnosis.user_id, activity_id)
        if existing is not None:
            return existing

        now = datetime.now(timezone.utc).isoformat()
        result_items = [common_api.serialization.to_data(item) for item in diagnosis.results]
        correct_count = sum(int(item.get("correct", 0)) for item in result_items)
        total_count = sum(int(item.get("total", 0)) for item in result_items)
        accuracy = correct_count / total_count if total_count else 0.0
        activity = LearningActivity(
            id=activity_id,
            user_id=diagnosis.user_id,
            created_at=now,
            updated_at=now,
            category="diagnostic",
            activity_type="diagnostic_completed",
            status="success",
            title="完成能力诊断",
            description=f"{diagnosis.learning_goal} · 正确 {correct_count}/{total_count}",
            occurred_at=now,
            book_id=diagnosis.book_id,
            result={
                "accuracy": accuracy,
                "correct_count": correct_count,
                "total_count": total_count,
                "knowledge_point_results": result_items,
            },
            detail={"diagnosis_id": diagnosis.diagnosis_id, "answer_records": diagnosis.answer_records},
            client_request_id=activity_id,
            source="diagnosis",
        )
        validated = validate_learning_activity(activity)
        self.store.save(path=self.reader.path, content=validated, mode="append")
        return activity

    def record_qa_started(
        self,
        *,
        user_id: str,
        book_id: str,
        conversation_id: str,
    ) -> LearningActivity:
        """记录一次资料问答会话的开始，并按会话 ID 做幂等处理。"""

        activity_id = f"activity_qa_started_{conversation_id}"
        existing = self.get_activity(user_id, activity_id)
        if existing is not None:
            return existing

        now = datetime.now(timezone.utc).isoformat()
        activity = LearningActivity(
            id=activity_id,
            user_id=user_id,
            created_at=now,
            updated_at=now,
            category="qa",
            activity_type="qa_started",
            status="in_progress",
            title="开始资料问答",
            description="围绕学习资料进行多轮问答",
            occurred_at=now,
            book_id=book_id,
            result={"message_count": 0},
            detail={"conversation_id": conversation_id},
            client_request_id=activity_id,
            source="web",
        )
        validated = validate_learning_activity(activity)
        self.store.save(path=self.reader.path, content=validated, mode="append")
        return activity

    def record_learning_event(
        self,
        *,
        user_id: str,
        task_id: str,
        event_type: str,
        status: str,
        task_title: str = "",
        plan_id: str = "",
        book_id: str = "",
        knowledge_point_ids: list[str] | None = None,
        detail: dict[str, Any] | None = None,
        client_request_id: str = "",
    ) -> LearningActivity:
        """将学习任务事件转换为可查询的学习记录并持久化。"""
        if event_type != "task_completed":
            raise common_api.errors.ValidationAppError(
                "unsupported learning event type",
                details={"event_type": event_type},
            )
        if status != "completed":
            raise common_api.errors.ValidationAppError(
                "task completion event requires completed status",
                details={"status": status},
            )

        # API 的任务状态与学习记录状态不同，完成事件统一记为 success。
        activity_status = "success"
        if activity_status not in {"success", "in_progress", "pending", "failed", "cancelled"}:
            raise common_api.errors.ValidationAppError(
                "unsupported learning event status",
                details={"status": status},
            )

        if client_request_id:
            existing = next(
                (item for item in self._read_activities() if item.user_id == user_id and item.client_request_id == client_request_id),
                None,
            )
            if existing is not None:
                return existing

        now = datetime.now(timezone.utc).isoformat()
        display_status = {
            "completed": "已完成",
            "in_progress": "进行中",
        }.get(status, status)
        display_task = task_title or "学习任务"
        activity = LearningActivity(
            id=f"activity_{event_type}_{task_id}_{uuid4().hex[:10]}",
            user_id=user_id,
            created_at=now,
            updated_at=now,
            category="task",
            activity_type=event_type,
            status=activity_status,
            title="完成学习任务",
        description=f"{display_task} 计划 {display_status}",
            occurred_at=now,
            book_id=book_id,
            plan_id=plan_id,
            task_id=task_id,
            knowledge_point_ids=knowledge_point_ids or [],
            result={"task_status": status, "task_status_label": display_status},
            detail={"task_title": display_task, **(detail or {})},
            client_request_id=client_request_id,
            source="web",
        )
        validated = validate_learning_activity(activity)
        self.store.save(path=self.reader.path, content=validated, mode="append")
        return activity

    def _read_activities(self) -> list[LearningActivity]:
        payload = self.reader.read(allow_missing=True, allow_empty=False)
        if payload == {}:
            return []
        if not isinstance(payload, list):
            raise common_api.errors.StorageReadError("learning activity resource must be a JSON array")

        activities: list[LearningActivity] = []
        for item in payload:
            validated = validate_learning_activity(item)
            activities.append(common_api.serialization.from_data(LearningActivity, validated))
        return activities
