"""今日学习接口的请求和响应模型。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class BookResponse(BaseModel):
    id: str
    title: str
    short_title: str = Field(alias="shortTitle")
    subtitle: str = ""

    model_config = ConfigDict(populate_by_name=True)


class DailyDurationResponse(BaseModel):
    date: str
    duration_seconds: int = Field(alias="durationSeconds")

    model_config = ConfigDict(populate_by_name=True)


class WeeklyProgressResponse(BaseModel):
    progress_percent: float = Field(alias="progressPercent")
    completed_task_count: int = Field(alias="completedTaskCount")
    total_task_count: int = Field(alias="totalTaskCount")
    study_duration_seconds: int = Field(alias="studyDurationSeconds")
    study_duration_hours: float = Field(alias="studyDurationHours")
    accuracy: float
    daily_duration: list[DailyDurationResponse] = Field(alias="dailyDuration")

    model_config = ConfigDict(populate_by_name=True)


class RecommendationResponse(BaseModel):
    task_id: str = Field(alias="taskId")
    title: str
    minutes: int
    difficulty: str = ""
    reason: str = ""
    priority: str = "highest"

    model_config = ConfigDict(populate_by_name=True)


class KnowledgeNodeResponse(BaseModel):
    id: str
    label: str
    status: str
    mastery_score: float | None = Field(default=None, alias="masteryScore")
    accuracy: float | None = None
    task_id: str | None = Field(default=None, alias="taskId")
    reason: str = ""
    description: str = ""

    model_config = ConfigDict(populate_by_name=True)


class KnowledgeGraphResponse(BaseModel):
    goal: str
    nodes: list[KnowledgeNodeResponse]


class TodayTaskResponse(BaseModel):
    id: str
    title: str
    type: str
    minutes: int
    status: Literal["completed", "in_progress", "todo", "review_due", "skipped", "rescheduled"]
    reason: str = ""
    description: str = ""
    knowledge_point_ids: list[str] = Field(default_factory=list, alias="knowledgePointIds")

    model_config = ConfigDict(populate_by_name=True)


class TaskSummaryResponse(BaseModel):
    completed: int
    total: int


class ContinueLearningResponse(BaseModel):
    task_id: str = Field(alias="taskId")
    title: str
    type: str
    minutes: int
    status: str
    expected_completion_date: str = Field(alias="expectedCompletionDate")
    description: str = ""
    reason: str = ""

    model_config = ConfigDict(populate_by_name=True)


class TodayLearningResponse(BaseModel):
    book: BookResponse
    goal: str
    last_learned: str = Field(alias="lastLearned")
    weekly_progress: WeeklyProgressResponse = Field(alias="weeklyProgress")
    recommendation: RecommendationResponse | None = None
    knowledge_graph: KnowledgeGraphResponse = Field(alias="knowledgeGraph")
    tasks: list[TodayTaskResponse]
    task_summary: TaskSummaryResponse = Field(alias="taskSummary")
    continue_learning: ContinueLearningResponse | None = Field(default=None, alias="continueLearning")

    model_config = ConfigDict(populate_by_name=True)
