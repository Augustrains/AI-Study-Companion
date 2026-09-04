"""学习目标：用户为某本书设定的目标水平与每周投入时长。

这是「选书与目标」页保存的东西，也是学习计划排课的输入之一：
    targetLevel  决定任务难度取向（复述概念 / 独立练习 / 进阶应用 / 面试）
    dailyMinutes 决定每天能安排多少学习任务
    targetDate   记录学习者希望完成目标的日期

生产环境通过 Repository 写入 MySQL 的 learning_goal 表；JSON 实现仅保留给测试和旧数据导入。
一个用户在同一本书上读取最新目标，保存时优先更新仍在进行的目标。
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from modules.common.errors import ValidationAppError

from .models import MAX_DAILY_MINUTES, TARGET_LEVELS, LearnerGoal
from .repository import JsonLearnerGoalRepository, LearnerGoalRepository

class LearnerGoalModule:
    DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "learner_goals" / "goals.json"

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        repository: LearnerGoalRepository | None = None,
    ) -> None:
        if path is not None and repository is not None:
            raise ValueError("path and repository cannot be provided together")
        self.repository = repository or JsonLearnerGoalRepository(path or self.DEFAULT_PATH)

    @staticmethod
    def key(user_id: str, book_id: str) -> str:
        return f"{user_id}:{book_id}"

    def get(self, *, user_id: str, book_id: str) -> LearnerGoal | None:
        return self.repository.get(user_id=user_id, book_id=book_id)

    def save(
        self,
        *,
        user_id: str,
        book_id: str,
        target_level: str,
        daily_minutes: int,
        target_date: str | None,
    ) -> LearnerGoal:
        if target_level not in TARGET_LEVELS:
            raise ValidationAppError(
                "unsupported target level",
                details={"target_level": target_level, "allowed": list(TARGET_LEVELS)},
            )
        if not 1 <= daily_minutes <= MAX_DAILY_MINUTES:
            raise ValidationAppError(
                "daily minutes out of range",
                details={"daily_minutes": daily_minutes, "min": 1, "max": MAX_DAILY_MINUTES},
            )
        if target_date is not None:
            try:
                parsed_target_date = date.fromisoformat(target_date)
            except ValueError as exc:
                raise ValidationAppError("target date must use YYYY-MM-DD", cause=exc) from exc
            if parsed_target_date < date.today():
                raise ValidationAppError("target date cannot be in the past")
        goal = LearnerGoal(
            goal_id=self.key(user_id, book_id),
            user_id=user_id,
            book_id=book_id,
            target_level=target_level,
            daily_minutes=int(daily_minutes),
            target_date=target_date,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        return self.repository.upsert(goal)

    # ---------- 供学习计划模块使用 ----------

    def daily_minutes_budget(self, *, user_id: str, book_id: str) -> int | None:
        """返回用户设定的每日学习分钟数；没设过目标时返回 None。"""
        goal = self.get(user_id=user_id, book_id=book_id)
        if goal is None:
            return None
        return max(15, goal.daily_minutes)
