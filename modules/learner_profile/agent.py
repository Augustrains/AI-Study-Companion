"""Two constrained Agents for goal requirements and current knowledge mastery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from modules.common.errors import ConfigurationError, ExternalServiceError
from sdk.llm_client import LLMClient, NullLLMClient


@dataclass(frozen=True)
class KnowledgePointAgentInput:
    background: str
    goal: str
    aim_level: int
    knowledge_points: list[dict[str, Any]]
    prior_mastery_scores: dict[int, float] | None = None
    self_assessed_level: str = "unknown"
    current_confusions: str = ""
    additional_requirements: str = ""
    preferred_activity_types: list[str] | None = None
    preferred_difficulty: str = "adaptive"
    learning_frequency: str = "flexible"
    session_duration_minutes: int | None = None

    # ``learning_goal.aim_level`` is intentionally stored as a stable numeric
    # value in MySQL.  Agents, however, should receive the learner's selected
    # level as an explicit natural-language constraint alongside the free-text
    # goal, rather than needing to infer what 0/1/2/3 means.
    AIM_LEVEL_DESCRIPTIONS = (
        "能够复述核心概念",
        "能够独立完成基础练习",
        "能够解决进阶应用问题",
        "能够指导他人 / 应对面试",
    )

    @property
    def aim_level_description(self) -> str:
        level = max(0, min(len(self.AIM_LEVEL_DESCRIPTIONS) - 1, int(self.aim_level)))
        return self.AIM_LEVEL_DESCRIPTIONS[level]

    @property
    def learning_goal_context(self) -> str:
        """The goal text supplied to agents, combining both persisted fields."""
        goal = self.goal.strip() or "未填写具体目标"
        return f"{goal}\n目标水平：{self.aim_level_description}"

    @property
    def learner_profile_context(self) -> str:
        """Non-score profile evidence available to the mastery assessment agent."""
        activities = "、".join(self.preferred_activity_types or []) or "未说明"
        duration = f"{self.session_duration_minutes} 分钟" if self.session_duration_minutes else "未说明"
        return (
            f"学习背景：{self.background.strip() or '未说明'}\n"
            f"自评水平：{self.self_assessed_level}\n"
            f"当前困惑：{self.current_confusions.strip() or '未说明'}\n"
            f"附加要求：{self.additional_requirements.strip() or '未说明'}\n"
            f"偏好活动：{activities}\n"
            f"难度倾向：{self.preferred_difficulty}\n"
            f"学习频率：{self.learning_frequency}\n"
            f"单次学习时长：{duration}"
        )


class _ConstrainedKnowledgePointAgent:
    response_key: str
    score_key: str

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or NullLLMClient()

    def analyze(self, agent_input: KnowledgePointAgentInput) -> dict[int, float]:
        fallback = self._fallback(agent_input)
        try:
            response = self.llm_client.generate(self._prompt(agent_input))
            return self._validate(response, agent_input.knowledge_points, fallback)
        except (ConfigurationError, ExternalServiceError, ValueError, TypeError, json.JSONDecodeError):
            return fallback

    def _fallback(self, agent_input: KnowledgePointAgentInput) -> dict[int, float]:
        raise NotImplementedError

    def _prompt(self, agent_input: KnowledgePointAgentInput) -> str:
        raise NotImplementedError

    def _validate(self, response: str, points: list[dict[str, Any]], fallback: dict[int, float]) -> dict[int, float]:
        raw = response.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.splitlines()[1:-1]).strip()
        payload = json.loads(raw)
        items = payload.get(self.response_key) if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise ValueError(f"{self.response_key} must be a list")
        values = dict(fallback)
        allowed = {int(point["id"]) for point in points}
        for item in items:
            if not isinstance(item, dict):
                continue
            point_id = int(item.get("knowledgePointId"))
            if point_id in allowed:
                values[point_id] = max(0.0, min(1.0, float(item.get(self.score_key))))
        return values


class GoalKnowledgeRequirementAgent(_ConstrainedKnowledgePointAgent):
    """Maps a final learning goal to required score for every supplied point."""

    response_key = "requirements"
    score_key = "aimScore"

    def _fallback(self, agent_input: KnowledgePointAgentInput) -> dict[int, float]:
        target = max(0.0, min(1.0, agent_input.aim_level / 3))
        return {int(point["id"]): target for point in agent_input.knowledge_points}

    def _prompt(self, agent_input: KnowledgePointAgentInput) -> str:
        context = {
            "finalGoal": agent_input.learning_goal_context,
            "overallAimLevel": agent_input.aim_level,
            "overallAimLevelDescription": agent_input.aim_level_description,
            "knowledgePoints": agent_input.knowledge_points,
        }
        return f"""你是学习目标分解 Agent。根据最终学习目标，为输入中每个既有知识点确定完成目标所需的目标掌握分数。只能使用输入中的 knowledgePointId；aimScore 为 0-1，表示达到目标所需水平，不是当前水平。所有知识点必须输出一次，不能创造知识点。只输出 JSON：{{\"requirements\":[{{\"knowledgePointId\":1,\"aimScore\":0.8}}]}}。\n输入：{json.dumps(context, ensure_ascii=False)}"""


class CurrentMasteryAssessmentAgent(_ConstrainedKnowledgePointAgent):
    """Estimates current mastery from user-provided background and prior records."""

    response_key = "assessments"
    score_key = "masteryScore"

    def _fallback(self, agent_input: KnowledgePointAgentInput) -> dict[int, float]:
        background = agent_input.background.lower()
        prior = agent_input.prior_mastery_scores or {}
        return {int(point["id"]): max(float(prior.get(int(point["id"]), 0.0)), 0.3 if str(point["name"]).lower() in background or str(point["code"]).lower() in background else 0.0) for point in agent_input.knowledge_points}

    def _prompt(self, agent_input: KnowledgePointAgentInput) -> str:
        context = {
            "learnerProfile": agent_input.learner_profile_context,
            "finalGoal": agent_input.learning_goal_context,
            "priorMasteryScores": agent_input.prior_mastery_scores or {},
            "knowledgePoints": agent_input.knowledge_points,
        }
        return f"""你是当前掌握度评估 Agent。根据用户学习背景、已有掌握记录和提供信息，评估输入中每个既有知识点的当前掌握分数。只能使用输入中的 knowledgePointId；masteryScore 为 0-1，不得把最终目标当作当前能力；已有掌握记录是重要证据，不能无理由降低。没有证据时取低分。所有知识点必须输出一次，不能创造知识点。只输出 JSON：{{\"assessments\":[{{\"knowledgePointId\":1,\"masteryScore\":0.2}}]}}。\n输入：{json.dumps(context, ensure_ascii=False)}"""
