"""Database-backed learner-profile setup service."""

from __future__ import annotations

from typing import Any

from .agent import CurrentMasteryAssessmentAgent, GoalKnowledgeRequirementAgent, KnowledgePointAgentInput
from .repository import MySqlLearnerProfileRepository


class MySqlLearnerProfileModule:
    def __init__(self, repository: MySqlLearnerProfileRepository, goal_agent: GoalKnowledgeRequirementAgent, mastery_agent: CurrentMasteryAssessmentAgent) -> None:
        self.repository, self.goal_agent, self.mastery_agent = repository, goal_agent, mastery_agent

    def books(self) -> list[dict[str, Any]]:
        return self.repository.books()

    def get_setup(self, user_id: int, book_id: int) -> dict[str, Any] | None:
        return self.repository.load(user_id, book_id)

    def save_setup(self, payload: dict[str, Any]) -> dict[str, Any]:
        points = self.repository.knowledge_points(int(payload["book_id"]))
        existing = self.repository.load(int(payload["user_id"]), int(payload["book_id"])) or {}
        prior_scores = {int(item["knowledge_point_id"]): float(item.get("mastery_score") or 0.0) for item in existing.get("mastery", [])}
        agent_input = KnowledgePointAgentInput(background=str(payload["background"]), goal=str(payload["goal"]), aim_level=int(payload["aim_level"]), knowledge_points=points, prior_mastery_scores=prior_scores)
        aim_scores = self.goal_agent.analyze(agent_input)
        mastery_scores = self.mastery_agent.analyze(agent_input)
        point_scores = {point_id: {"aim_score": aim_scores[point_id], "mastery_score": mastery_scores[point_id], "confidence": 0.35 if mastery_scores[point_id] > 0 else 0.2} for point_id in aim_scores}
        return self.repository.save(payload, point_scores)
