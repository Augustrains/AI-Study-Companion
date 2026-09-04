"""学习目标数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# The database stores the selected level as its stable 0-3 position.
TARGET_LEVELS = (
    "能够复述核心概念",
    "能够独立完成基础练习",
    "能够解决进阶应用问题",
    "能够指导他人 / 应对面试",
)

MAX_DAILY_MINUTES = 1440


@dataclass
class LearnerGoal:
    goal_id: str
    user_id: str
    book_id: str
    target_level: str
    daily_minutes: int
    target_date: str | None
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "user_id": self.user_id,
            "book_id": self.book_id,
            "target_level": self.target_level,
            "daily_minutes": self.daily_minutes,
            "target_date": self.target_date,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LearnerGoal":
        return cls(
            goal_id=str(payload.get("goal_id", "")),
            user_id=str(payload.get("user_id", "")),
            book_id=str(payload.get("book_id", "")),
            target_level=str(payload.get("target_level", "")),
            daily_minutes=int(
                payload.get("daily_minutes", 0)
                or round(float(payload.get("weekly_hours", 0) or 0) * 60 / 7)
            ),
            target_date=str(payload["target_date"]) if payload.get("target_date") else None,
            updated_at=str(payload.get("updated_at", "")),
        )

    def public_view(self) -> dict[str, Any]:
        """返回给前端的形状，与 services/api.ts 的 LearnerGoalResult 对齐。"""
        return {
            "goalId": self.goal_id,
            "userId": self.user_id,
            "bookId": self.book_id,
            "targetLevel": self.target_level,
            "dailyMinutes": self.daily_minutes,
            "targetDate": self.target_date,
            "updatedAt": self.updated_at,
        }
