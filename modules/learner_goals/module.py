"""学习目标：用户为某本书设定的目标水平与每周投入时长。

这是「选书与目标」页保存的东西，也是学习计划排课的输入之一：
    targetLevel  决定任务难度取向（复述概念 / 独立练习 / 进阶应用 / 面试）
    weeklyHours  决定一周能排多少任务时长

存储：data/learner_goals/goals.json，按 "{user_id}:{book_id}" 单条 upsert。
一个用户在同一本书上只保留最新的一份目标，改目标就是覆盖。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.common import api as common_api
from modules.common.errors import ValidationAppError

from .models import LearnerGoal

# 目标水平白名单，与前端 GoalsSetupView 的 TARGET_LEVELS 一一对应。
# 放在后端是因为它会影响排课，不能由前端随便传一个字符串进来。
TARGET_LEVELS = (
    "能够复述核心概念",
    "能够独立完成基础练习",
    "能够解决进阶应用问题",
    "能够指导他人 / 应对面试",
)

MAX_WEEKLY_HOURS = 80


class LearnerGoalModule:
    DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "learner_goals" / "goals.json"

    def __init__(self, path: str | Path | None = None) -> None:
        target = Path(path) if path is not None else self.DEFAULT_PATH
        self.reader = common_api.json_storage.JsonContentReader(target)
        self.store = common_api.json_storage.JsonStore()

    @staticmethod
    def key(user_id: str, book_id: str) -> str:
        return f"{user_id}:{book_id}"

    def _read_all(self) -> dict[str, Any]:
        payload = self.reader.read(allow_missing=True, allow_empty=False)
        if payload == {} or payload is None:
            return {}
        if not isinstance(payload, dict):
            raise common_api.errors.StorageReadError("learner goal resource must be a JSON object")
        return payload

    def get(self, *, user_id: str, book_id: str) -> LearnerGoal | None:
        row = self._read_all().get(self.key(user_id, book_id))
        return LearnerGoal.from_dict(row) if isinstance(row, dict) else None

    def save(self, *, user_id: str, book_id: str, target_level: str, weekly_hours: float) -> LearnerGoal:
        if target_level not in TARGET_LEVELS:
            raise ValidationAppError(
                "unsupported target level",
                details={"target_level": target_level, "allowed": list(TARGET_LEVELS)},
            )
        if not 1 <= weekly_hours <= MAX_WEEKLY_HOURS:
            raise ValidationAppError(
                "weekly hours out of range",
                details={"weekly_hours": weekly_hours, "min": 1, "max": MAX_WEEKLY_HOURS},
            )
        goal = LearnerGoal(
            goal_id=self.key(user_id, book_id),
            user_id=user_id,
            book_id=book_id,
            target_level=target_level,
            weekly_hours=float(weekly_hours),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self.store.save(
            path=self.reader.path,
            content=goal.to_dict(),
            mode="upsert",
            key_path=[goal.goal_id],
        )
        return goal

    # ---------- 供学习计划模块使用 ----------

    def daily_minutes_budget(self, *, user_id: str, book_id: str) -> int | None:
        """把每周小时数折算成每天可排的分钟数；没设过目标时返回 None。

        按 7 天摊平而不是按「工作日」，因为学习频率是用户在学习画像里
        单独选的，这里不该替他假设哪几天学。
        """
        goal = self.get(user_id=user_id, book_id=book_id)
        if goal is None:
            return None
        return max(15, int(round(goal.weekly_hours * 60 / 7)))
