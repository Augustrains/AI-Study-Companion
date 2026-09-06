"""Database-backed learner-profile setup service."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
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
        agent_input = KnowledgePointAgentInput(
            background=str(payload["background"]),
            goal=str(payload["goal"]),
            aim_level=int(payload["aim_level"]),
            knowledge_points=points,
            prior_mastery_scores=prior_scores,
            self_assessed_level=str(payload.get("self_assessed_level") or "unknown"),
            current_confusions=str(payload.get("current_confusions") or ""),
            additional_requirements=str(payload.get("additional_requirements") or ""),
            preferred_activity_types=list(payload.get("preferred_activity_types") or []),
            preferred_difficulty=str(payload.get("preferred_difficulty") or "adaptive"),
            learning_frequency=str(payload.get("learning_frequency") or "flexible"),
            session_duration_minutes=payload.get("session_duration_minutes"),
        )
        # 两个画像分析相互独立，并行调用可避免重建画像时串行等待两次
        # LLM 响应（每次最多 120 秒）导致前端长时间无响应。
        executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="profile-agent")
        aim_future = executor.submit(self.goal_agent.analyze, agent_input)
        mastery_future = executor.submit(self.mastery_agent.analyze, agent_input)
        try:
            aim_scores = aim_future.result(timeout=45)
            mastery_scores = mastery_future.result(timeout=45)
        except FuturesTimeoutError:
            # 外部模型不可用时不能让画像保存卡满两个 120 秒请求；
            # 立即采用确定性的本地估计，后台线程随后自行结束。
            aim_scores = self.goal_agent._fallback(agent_input)
            mastery_scores = self.mastery_agent._fallback(agent_input)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        point_scores = {point_id: {"aim_score": aim_scores[point_id], "mastery_score": mastery_scores[point_id], "confidence": 0.35 if mastery_scores[point_id] > 0 else 0.2} for point_id in aim_scores}
        return self.repository.save(payload, point_scores)
