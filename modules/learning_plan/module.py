"""Database-backed seven-day learning-plan workflow."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from modules.common.errors import ValidationAppError
from modules.diagnosis.mastery_rules import calculate_mastery_update

from .agent import WeeklyLearningPlanAgent, WeeklyPlanningInput
from .bkt import BktMasteryEstimator
from .materials import ReadingMaterialService
from .mastery_fusion import MasteryFusion
from .pace import LearningPaceAgent
from .repository import MySqlLearningPlanRepository


class LearningPlanModule:
    def __init__(self, repository: MySqlLearningPlanRepository, estimator: BktMasteryEstimator | None = None, agent: WeeklyLearningPlanAgent | None = None, materials: ReadingMaterialService | None = None, mastery_fusion: MasteryFusion | None = None, pace_agent: LearningPaceAgent | None = None) -> None:
        self.repository = repository
        self.estimator = estimator or BktMasteryEstimator()
        self.agent = agent or WeeklyLearningPlanAgent()
        self.materials = materials or ReadingMaterialService()
        self.mastery_fusion = mastery_fusion or MasteryFusion()
        self.pace_agent = pace_agent

    def _pace_factors(self, context: dict[str, Any]) -> dict[str, float]:
        if self.pace_agent is None:
            return {}
        return self.pace_agent.factors(user_id=str(context["user_id"]), book_id=str(context["book"]["id"]))

    def get_weekly(self, *, user_id: int, book_id: int) -> dict[str, Any] | None:
        return self.repository.load_active_weekly_plan(user_id=user_id, book_id=book_id)

    def get_reading_materials(self, *, book_id: int, item_title: str) -> dict[str, Any]:
        knowledge_point = self.repository.find_reading_knowledge_point(book_id=book_id, item_title=item_title)
        if knowledge_point is None:
            raise ValidationAppError("reading task is not linked to a knowledge point", details={"item_title": item_title, "book_id": book_id})
        return self.materials.lookup(book_id=book_id, item_title=item_title, knowledge_point=knowledge_point)

    def complete_item(self, *, user_id: int, item_id: int) -> dict[str, Any]:
        return self.repository.complete_weekly_plan_item(user_id=user_id, item_id=item_id)

    def generate_weekly(self, *, user_id: int, book_id: int, start_date: date | None = None) -> dict[str, Any]:
        context = self.repository.load_weekly_context(user_id=user_id, book_id=book_id)
        if int(context["goal"].get("daily_minutes") or 0) < self.agent.DIAGNOSTIC_MINUTES:
            raise ValidationAppError(f"daily_minutes must be at least {self.agent.DIAGNOSTIC_MINUTES}")
        workloads = [self._workload(point, context) for point in context["points"]]
        generated = self.agent.build(WeeklyPlanningInput(context=context, workloads=workloads, start_date=start_date or date.today(), pace_factors=self._pace_factors(context)))
        plan_id = self.repository.replace_weekly_plan(context=context, days=generated["days"])
        return {"plan_id": plan_id, "user_id": user_id, "book": context["book"], "goal": context["goal"], "fixed_minutes": {"reading": self.agent.READING_MINUTES, "practice_per_opportunity": self.agent.PRACTICE_MINUTES, "daily_diagnostic": self.agent.DIAGNOSTIC_MINUTES}, "knowledge_point_workloads": workloads, "deferred_knowledge_point_ids": generated["deferred_knowledge_point_ids"], "days": generated["days"]}

    def replan_after_diagnostic(self, *, plan_id: int, diagnostic_session_id: int, rule_results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        loaded = self.repository.load_replan_context(plan_id=plan_id, diagnostic_session_id=diagnostic_session_id)
        context, binding = loaded["context"], loaded["binding"]
        updates: dict[int, dict[str, Any]] = {}
        rules_by_code = {str(item.get("knowledge_point_id")): item for item in (rule_results or []) if item.get("knowledge_point_id")}
        for point in context["points"]:
            point_id = int(point["knowledge_point_id"])
            outcomes = loaded["outcomes"].get(point_id, [])
            if not outcomes:
                continue
            estimate = self.estimator.estimate(current_mastery=float(point["mastery_score"]), target_mastery=float(point["aim_score"]), outcomes=outcomes, stored_confidence=float(point.get("confidence") or 0))
            rule_update = rules_by_code.get(str(point.get("knowledge_point_code"))) or self._rule_update_from_outcomes(point, outcomes, diagnostic_session_id)
            fused = self.mastery_fusion.combine(bkt=estimate, rule_update=rule_update)
            updates[point_id] = {"mastery_score": fused.mastery_score, "confidence": fused.confidence, "next_review_at": fused.next_review_at}
        self.repository.update_mastery_scores(user_id=int(context["user_id"]), goal_id=int(context["goal"]["id"]), scores=updates)
        refreshed = self.repository.load_weekly_context(user_id=int(context["user_id"]), book_id=int(context["book"]["id"]))
        workloads = [self._workload(point, {**refreshed, "outcomes": {}}) for point in refreshed["points"]]
        after_date = binding["expected_date"]
        window_end_date = binding["window_end_date"]
        if isinstance(after_date, str):
            after_date = date.fromisoformat(after_date)
        if isinstance(window_end_date, str):
            window_end_date = date.fromisoformat(window_end_date)
        # Future-day replacement must start tomorrow. Rebuilding from day one
        # while preserving today used to discard a newly scheduled reading or
        # first practice opportunity.
        remaining_days = max(0, (window_end_date - after_date).days)
        generated = self.agent.build(
            WeeklyPlanningInput(
                context=refreshed,
                workloads=workloads,
                start_date=after_date + timedelta(days=1),
                plan_days=remaining_days,
                pace_factors=self._pace_factors(refreshed),
            )
        )
        self.repository.replace_future_days(plan_id=plan_id, after_date=binding["expected_date"], days=generated["days"])
        return {"plan_id": plan_id, "diagnostic_session_id": diagnostic_session_id, "updated_mastery": updates, "retained_through": str(binding["expected_date"]), "days": generated["days"]}

    @staticmethod
    def _rule_update_from_outcomes(point: dict[str, Any], outcomes: list[bool], session_id: int) -> dict[str, Any]:
        """Compatibility fallback when a legacy caller has no rich rule result."""

        return calculate_mastery_update(
            {
                "currentState": {"masteryScore": float(point["mastery_score"])},
                "evidence": [
                    {
                        "evidenceId": f"{session_id}:{point['knowledge_point_id']}:{index}",
                        "score": 1.0 if correct else 0.0,
                        "isCorrect": correct,
                        "evidenceStrength": "direct",
                        "taskMode": "diagnostic",
                        "hintCount": 0,
                        "retryCount": 0,
                        "isIndependent": True,
                        "isDelayedRetrieval": False,
                    }
                    for index, correct in enumerate(outcomes, start=1)
                ],
            }
        )

    def _workload(self, point: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        point_id = int(point["knowledge_point_id"])
        estimate = self.estimator.estimate(current_mastery=float(point.get("mastery_score") or 0), target_mastery=float(point.get("aim_score") or 0), outcomes=context["outcomes"].get(point_id, []), stored_confidence=float(point.get("confidence") or 0))
        gap = max(float(point.get("aim_score") or 0) - estimate.mastery_score, 0.0)
        priority = gap * (1.0 + (1.0 - estimate.confidence))
        return {**point, "mastery_score": estimate.mastery_score, "predicted_correct_rate": estimate.predicted_correct_rate, "learning_rate": estimate.learning_rate, "expected_practice_count": estimate.expected_practice_count, "confidence": estimate.confidence, "gap_score": round(gap, 4), "priority_score": round(priority, 4), "question_ids": context["question_ids"].get(point_id, [])}
