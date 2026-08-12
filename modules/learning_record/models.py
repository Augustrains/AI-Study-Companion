"""学习记录/最近活动的领域模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modules.common import api as common_api


# 活动所属的一级业务分类。
ACTIVITY_CATEGORIES = ("profile", "qa", "diagnostic", "task")

# 活动的具体行为类型。
ACTIVITY_TYPES = (
    "profile_created",
    "profile_updated",
    "qa_started",
    "qa_asked",
    "qa_answered",
    "diagnostic_started",
    "diagnostic_completed",
    "diagnostic_calibrated",
    "review_completed",
    "task_completed",
)

# 活动当前的处理状态。
ACTIVITY_STATUSES = (
    "success",
    "in_progress",
    "pending",
    "failed",
    "cancelled",
)


@dataclass
class LearningActivity(
    common_api.models.Identified,
    common_api.models.UserOwned,
    common_api.models.Timestamped,
):
    """一条可展示在最近活动中的学习活动记录。"""

    # 活动所属分类：人物画像、资料问答、能力诊断或学习任务。
    category: str = ""
    # 活动的具体类型，例如 task_completed、diagnostic_completed。
    activity_type: str = ""
    # 活动状态，例如成功、进行中、待处理或失败。
    status: str = "success"
    # 前端列表中展示的活动标题。
    title: str = ""
    # 前端列表中展示的活动摘要或描述。
    description: str = ""
    # 活动实际发生的时间，使用带时区的 ISO 时间字符串。
    occurred_at: str = ""

    # 关联的学习内容、教材或课程 ID。
    book_id: str = ""
    # 关联的学习目标 ID。
    learning_goal_id: str = ""
    # 关联的学习计划 ID。
    plan_id: str = ""
    # 关联的学习任务 ID。
    task_id: str = ""
    # 关联的能力诊断会话 ID。
    diagnostic_id: str = ""
    # 关联的资料问答会话 ID。
    qa_conversation_id: str = ""
    # 关联的人物画像 ID。
    learner_profile_id: str = ""
    # 活动关联的知识点 ID 列表。
    knowledge_point_ids: list[str] = field(default_factory=list)

    # 活动产生的结构化结果，例如正确率、得分、掌握度和学习时长。
    result: dict[str, Any] = field(default_factory=dict)
    # 活动详情扩展数据，保存不同活动类型的专属信息。
    detail: dict[str, Any] = field(default_factory=dict)

    # 前端请求的幂等 ID，用于避免同一活动被重复提交。
    client_request_id: str = ""
    # 活动来源，例如 web、mobile 或 system。
    source: str = "web"
