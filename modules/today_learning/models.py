"""今日学习页面使用的领域模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WeeklyProgress:
    progress_percent: float = 0
    completed_task_count: int = 0
    total_task_count: int = 0
    study_duration_seconds: int = 0
    accuracy: float = 0
    daily_duration: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TodayLearning:
    book: dict[str, str]
    goal: str = ""
    last_learned: str = ""
    weekly_progress: WeeklyProgress = field(default_factory=WeeklyProgress)
    recommendation: dict[str, Any] = field(default_factory=dict)
    knowledge_graph: dict[str, Any] = field(default_factory=dict)
    tasks: list[dict[str, Any]] = field(default_factory=list)

