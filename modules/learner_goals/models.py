"""学习目标数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LearnerGoal:
    goal_id: str
    user_id: str
    book_id: str
    target_level: str
    weekly_hours: float
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "user_id": self.user_id,
            "book_id": self.book_id,
            "target_level": self.target_level,
            "weekly_hours": self.weekly_hours,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LearnerGoal":
        return cls(
            goal_id=str(payload.get("goal_id", "")),
            user_id=str(payload.get("user_id", "")),
            book_id=str(payload.get("book_id", "")),
            target_level=str(payload.get("target_level", "")),
            weekly_hours=float(payload.get("weekly_hours", 0) or 0),
            updated_at=str(payload.get("updated_at", "")),
        )

    def public_view(self) -> dict[str, Any]:
        """返回给前端的形状，与 services/api.ts 的 LearnerGoalResult 对齐。"""
        return {
            "goalId": self.goal_id,
            "userId": self.user_id,
            "bookId": self.book_id,
            "targetLevel": self.target_level,
            "weeklyHours": self.weekly_hours,
            "updatedAt": self.updated_at,
        }
