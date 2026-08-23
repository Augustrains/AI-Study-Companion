"""今日学习页面使用的领域模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


#表示本周学习进度
@dataclass
class WeeklyProgress:
    progress_percent: float = 0  #进度百分比
    completed_task_count: int = 0  #已完成任务数
    total_task_count: int = 0      #任务总数
    study_duration_seconds: int = 0  #学习时长
    accuracy: float = 0             #正确率
    daily_duration: list[dict[str, Any]] = field(default_factory=list)  #每日学习时长明细


#今日学习页面的整体数据
@dataclass
class TodayLearning:
    book: dict[str, str]  #当前学习书籍
    goal: str = ""        #学习目标
    last_learned: str = ""  #上次学习内容
    weekly_progress: WeeklyProgress = field(default_factory=WeeklyProgress)
    recommendation: dict[str, Any] = field(default_factory=dict)    #学习推荐
    knowledge_graph: dict[str, Any] = field(default_factory=dict)   #知识图谱
    tasks: list[dict[str, Any]] = field(default_factory=list)       #今日任务列表

