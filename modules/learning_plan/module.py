"""Database-backed seven-day learning-plan workflow."""

from __future__ import annotations

from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from threading import Thread
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
    def __init__(self, repository: MySqlLearningPlanRepository, estimator: BktMasteryEstimator | None = None, agent: WeeklyLearningPlanAgent | None = None, materials: ReadingMaterialService | None = None, mastery_fusion: MasteryFusion | None = None, pace_agent: LearningPaceAgent | None = None, question_bank: Any | None = None) -> None:
        self.repository = repository
        self.estimator = estimator or BktMasteryEstimator()
        self.agent = agent or WeeklyLearningPlanAgent()
        self.materials = materials or ReadingMaterialService()
        self.mastery_fusion = mastery_fusion or MasteryFusion()
        self.pace_agent = pace_agent
        self.question_bank = question_bank

    def _pace_factors(self, context: dict[str, Any]) -> dict[str, float]:
        if self.pace_agent is None:
            return {}
        return self.pace_agent.factors(user_id=str(context["user_id"]), book_id=str(context["book"]["id"]))

    def get_weekly(self, *, user_id: int, book_id: int) -> dict[str, Any] | None:
        close_overdue = getattr(self.repository, "close_overdue_items", None)
        if close_overdue is not None:
            close_overdue(user_id=user_id, book_id=book_id)
        return self.repository.load_active_weekly_plan(user_id=user_id, book_id=book_id)

    def ensure_daily_diagnostic(self, *, user_id: int, book_id: int, scheduled_date: date | None = None) -> dict[str, Any] | None:
        """Materialise just today's opening diagnostic when it is first viewed."""

        scheduled = scheduled_date or date.today()
        day = self.repository.load_plan_day(
            user_id=user_id,
            book_id=book_id,
            expected_date=scheduled,
        )
        if day is None or day.get("items"):
            return self.get_weekly(user_id=user_id, book_id=book_id)
        context = self.repository.load_weekly_context(user_id=user_id, book_id=book_id)
        workloads = [self._workload(point, context) for point in context["points"]]
        generated = self.agent.build_daily_diagnostic(
            context=context,
            workloads=workloads,
            scheduled=scheduled,
        )
        self.repository.append_day_items(day_id=int(day["id"]), items=generated["items"])
        return self.get_weekly(user_id=user_id, book_id=book_id)

    def get_reading_materials(self, *, book_id: int, item_title: str) -> dict[str, Any]:
        cached = self.repository.find_prepared_reading(book_id=book_id, item_title=item_title)
        if cached is not None and int(cached.get("format_version", 0)) >= ReadingMaterialService.FORMAT_VERSION:
            return cached
        knowledge_point = self.repository.find_reading_knowledge_point(book_id=book_id, item_title=item_title)
        if knowledge_point is None:
            raise ValidationAppError("reading task is not linked to a knowledge point", details={"item_title": item_title, "book_id": book_id})
        return self.materials.lookup(book_id=book_id, item_title=item_title, knowledge_point=knowledge_point)

    def _prepare_plan_content(self, *, plan_id: int, context: dict[str, Any]) -> dict[str, int]:
        """Prepare every diagnostic and reading payload concurrently and persist it."""
        if self.question_bank is None:
            return {"completed": 0, "failed": 0}
        items = self.repository.load_plan_items(plan_id=plan_id)
        points = {int(point["knowledge_point_id"]): point for point in context["points"]}
        book_code = "ml-001" if int(context["book"]["id"]) == 2 else "dl-001"

        def prepare(item: dict[str, Any]) -> None:
            item_id = int(item["id"])
            try:
                title = str(item["title"])
                point = points.get(self._point_id_from_title(title, points))
                if str(item.get("source")) == "review_due":
                    if point is None:
                        raise ValidationAppError("diagnostic task has no knowledge point")
                    scheduled = item.get("expected_date")
                    if isinstance(scheduled, str):
                        scheduled = date.fromisoformat(scheduled[:10])
                    focus_id = self._point_id_from_title(title, points)
                    focus_ids = [focus_id] + [candidate_id for candidate_id in points if candidate_id != focus_id]
                    due_ids = [candidate_id for candidate_id in focus_ids[1:] if self._review_due_on(points[candidate_id].get("next_review_at"), scheduled)]
                    current_ids = [candidate_id for candidate_id in focus_ids if candidate_id not in due_ids]

                    def select(ids: list[int], limit: int, seed: str) -> tuple[list[Any], dict[str, str]]:
                        plan = {str(points[candidate_id]["knowledge_point_code"]): {"question_count": 4, "task_mode": "diagnostic"} for candidate_id in ids}
                        if not plan:
                            return [], {}
                        selected, selected_answers = self.question_bank.get_questions(book_code, question_plan=plan, rotation_seed=seed)
                        return selected[:limit], {question.id: selected_answers[question.id] for question in selected[:limit] if question.id in selected_answers}

                    # Six questions establish today's baseline; two due-review
                    # questions check retention of previously completed work.
                    questions, answers = select(current_ids, 6, f"plan:{plan_id}:item:{item_id}:current")
                    historical, historical_answers = select(due_ids, 2, f"plan:{plan_id}:item:{item_id}:history")
                    seen_ids = {question.id for question in questions}
                    questions.extend(question for question in historical if question.id not in seen_ids)
                    answers.update({question_id: value for question_id, value in historical_answers.items() if question_id in {question.id for question in questions}})
                    if len(questions) < 8:
                        fallback, fallback_answers = select([candidate_id for candidate_id in focus_ids if candidate_id not in due_ids], 8 - len(questions), f"plan:{plan_id}:item:{item_id}:fallback")
                        for question in fallback:
                            if question.id not in {item.id for item in questions}:
                                questions.append(question)
                                if question.id in fallback_answers:
                                    answers[question.id] = fallback_answers[question.id]
                    questions = questions[:8]
                    questions = questions[:8]
                    answers = {question.id: answers[question.id] for question in questions if question.id in answers}
                    from modules.diagnosis.services import DiagnosisService
                    payload = {"format_version": 2, "kind": "diagnostic", "questions": [DiagnosisService.question_payload(q) for q in questions], "correct_answers": answers}
                elif title.startswith("练习：") or title.startswith("复习："):
                    if point is None:
                        raise ValidationAppError("practice task has no knowledge point")
                    code = str(point.get("knowledge_point_code"))
                    selected, selected_answers = self.question_bank.get_questions(
                        book_code,
                        question_plan={code: {"question_count": 4, "task_mode": "independent"}},
                        rotation_seed=f"plan:{plan_id}:item:{item_id}:practice",
                    )
                    from modules.diagnosis.services import DiagnosisService
                    selected = selected[:4]
                    payload = {"format_version": 2, "kind": "practice", "questions": [DiagnosisService.question_payload(q) for q in selected], "correct_answers": {q.id: selected_answers[q.id] for q in selected if q.id in selected_answers}}
                elif title.startswith("阅读："):
                    if point is None:
                        raise ValidationAppError("reading task has no knowledge point")
                    material_point = {**point, "id": point.get("knowledge_point_id"), "name": point.get("knowledge_point_name"), "code": point.get("knowledge_point_code")}
                    payload = {"kind": "reading", **self.materials.lookup(book_id=int(context["book"]["id"]), item_title=title, knowledge_point=material_point)}
                else:
                    return
                self.repository.save_prepared_content(item_id=item_id, status="ready", payload=json.dumps(payload, ensure_ascii=False))
            except Exception as exc:  # one task must not cancel other preparations
                self.repository.save_prepared_content(item_id=item_id, status="failed", error=str(exc)[:1000])
                raise

        completed = failed = 0
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(items))), thread_name_prefix="plan-content") as pool:
            futures = [pool.submit(prepare, item) for item in items if str(item.get("source")) == "review_due" or str(item.get("title", "")).startswith(("阅读：", "练习：", "复习："))]
            for future in as_completed(futures):
                try:
                    future.result(); completed += 1
                except Exception:
                    failed += 1
        return {"completed": completed, "failed": failed}

    def _start_prepare_plan_content(self, *, plan_id: int, context: dict[str, Any]) -> dict[str, int]:
        """Queue content preparation and return without waiting for model/network calls."""
        if self.question_bank is None or not hasattr(self.repository, "load_plan_items"):
            return {"queued": 0, "completed": 0, "failed": 0}
        items = self.repository.load_plan_items(plan_id=plan_id)
        targets = [item for item in items if str(item.get("source")) == "review_due" or str(item.get("title", "")).startswith(("阅读：", "练习：", "复习："))]
        for item in targets:
            self.repository.save_prepared_content(item_id=int(item["id"]), status="pending")
        Thread(target=self._prepare_plan_content, kwargs={"plan_id": plan_id, "context": context}, name=f"plan-preparation-{plan_id}", daemon=True).start()
        return {"queued": len(targets), "completed": 0, "failed": 0}

    @staticmethod
    def _point_id_from_title(title: str, points: dict[int, dict[str, Any]]) -> int:
        for point_id, point in points.items():
            if str(point.get("knowledge_point_name")) in title:
                return point_id
        return 0

    @staticmethod
    def _review_due_on(value: Any, scheduled: date | None) -> bool:
        if not value or scheduled is None:
            return False
        try:
            review_date = value.date() if hasattr(value, "date") else date.fromisoformat(str(value)[:10])
            return review_date <= scheduled
        except (TypeError, ValueError):
            return False

    def complete_item(self, *, user_id: int, item_id: int) -> dict[str, Any]:
        result = self.repository.complete_weekly_plan_item(user_id=user_id, item_id=item_id)
        # Completing the final item (or returning after the 7-day window has
        # expired) automatically starts the next adaptive weekly plan.
        needs_rollover = getattr(self.repository, "plan_requires_rollover", None)
        if needs_rollover is not None and needs_rollover(user_id=user_id, item_id=item_id):
            try:
                item_context = self.repository.load_item_context(user_id=user_id, item_id=item_id)
                if item_context:
                    Thread(
                        target=self.generate_weekly,
                        kwargs={"user_id": user_id, "book_id": int(item_context["book_id"]),
                                "start_date": date.today(), "reason": "上一周期已结束，自动开启新一轮自适应计划。"},
                        name=f"auto-weekly-plan-{user_id}", daemon=True,
                    ).start()
                    result["next_plan_pending"] = True
            except Exception:
                # Task completion must remain durable even if asynchronous
                # regeneration is temporarily unavailable.
                result["next_plan_pending"] = True
        return result

    def generate_weekly(self, *, user_id: int, book_id: int, start_date: date | None = None, reason: str = "") -> dict[str, Any]:
        # Compatibility path for profiles saved before mastery rows became part
        # of the setup transaction.  The repository only inserts absent rows.
        initialize_mastery = getattr(self.repository, "ensure_initial_mastery_records", None)
        if initialize_mastery is not None:
            initialize_mastery(user_id=user_id, book_id=book_id)
        ensure_schema = getattr(self.repository, "ensure_prepared_content_schema", None)
        if ensure_schema is not None:
            ensure_schema()
        context = self.repository.load_weekly_context(user_id=user_id, book_id=book_id)
        if int(context["goal"].get("daily_minutes") or 0) < self.agent.DIAGNOSTIC_MINUTES:
            raise ValidationAppError(f"daily_minutes must be at least {self.agent.DIAGNOSTIC_MINUTES}")
        workloads = [self._workload(point, context) for point in context["points"]]
        generated = self.agent.build(
            WeeklyPlanningInput(
                context=context,
                workloads=workloads,
                start_date=start_date or date.today(),
                pace_factors=self._pace_factors(context),
                regeneration_reason=reason.strip(),
            )
        )
        plan_id = self.repository.replace_weekly_plan(context=context, days=generated["days"])
        prepared = self._start_prepare_plan_content(plan_id=plan_id, context=context)
        return {"plan_id": plan_id, "user_id": user_id, "book": context["book"], "goal": context["goal"], "fixed_minutes": {"reading": self.agent.READING_MINUTES, "practice_per_opportunity": self.agent.PRACTICE_MINUTES, "daily_diagnostic": self.agent.DIAGNOSTIC_MINUTES}, "knowledge_point_workloads": workloads, "deferred_knowledge_point_ids": generated["deferred_knowledge_point_ids"], "prepared_content": prepared, "regeneration_reason": reason.strip(), "advice": generated.get("advice", []), "resources": generated.get("resources", []), "days": generated["days"]}

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
        # Agent receives only the remaining date range and therefore starts
        # its local index at zero. Preserve the original week numbering so
        # tomorrow is 第 2 天 rather than another 第 1 天.
        window_start = binding.get("window_start_date") or after_date
        if isinstance(window_start, str):
            window_start = date.fromisoformat(window_start[:10])
        for offset, day in enumerate(generated["days"], start=1):
            day["title"] = f"第 {(after_date - window_start).days + offset + 1} 天学习计划"
        self.repository.replace_future_days(plan_id=plan_id, after_date=binding["expected_date"], days=generated["days"])
        prepared = self._start_prepare_plan_content(plan_id=plan_id, context=refreshed)
        return {"plan_id": plan_id, "diagnostic_session_id": diagnostic_session_id, "updated_mastery": updates, "retained_through": str(binding["expected_date"]), "prepared_content": prepared, "days": generated["days"]}

    @staticmethod
    def _apply_time_budget(plan: dict[str, Any], *, daily_budget: int | None, pace_factor: float = 1.0, only_unfinished: bool = False) -> dict[str, Any]:
        """Distribute tasks across calendar days without changing task durations."""
        tasks = plan.get("tasks")
        if not daily_budget or not isinstance(tasks, list) or not tasks:
            return plan
        factor = max(0.1, float(pace_factor or 1.0)); today = date.today(); day_index = 0; used = 0.0; scheduled = []
        for item in tasks:
            if not isinstance(item, dict): scheduled.append(item); continue
            if only_unfinished and item.get("status") == "completed": scheduled.append(item); continue
            minutes = int(item.get("minutes") or 0); occupied = minutes * factor
            if used and used + occupied > daily_budget: day_index += 1; used = 0.0
            used += occupied; task = dict(item); task["expectedCompletionDate"] = (today + timedelta(days=day_index)).isoformat(); scheduled.append(task)
        total = sum(int(item.get("minutes") or 0) for item in scheduled if isinstance(item, dict) and not (only_unfinished and item.get("status") == "completed"))
        updated = dict(plan); updated["tasks"] = scheduled; updated["timeBudget"] = {"dailyMinutes": daily_budget, "totalMinutes": total, "estimatedDays": day_index + 1, "paceFactor": round(factor, 2), "adjustedTotalMinutes": int(round(total * factor))}
        return updated

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
