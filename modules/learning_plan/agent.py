"""Deterministic seven-day planning agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class WeeklyPlanningInput:
    context: dict[str, Any]
    workloads: list[dict[str, Any]]
    start_date: date
    plan_days: int = 7
    pace_factors: dict[str, float] = field(default_factory=dict)


class WeeklyLearningPlanAgent:
    """Turn BKT opportunities into a paced, prerequisite-safe study plan."""

    READING_MINUTES = 15
    PRACTICE_MINUTES = 3
    DIAGNOSTIC_MINUTES = 10
    PLAN_DAYS = 7
    MAX_ACTIVE_KNOWLEDGE_POINTS = 3

    def build(self, agent_input: WeeklyPlanningInput) -> dict[str, Any]:
        daily_minutes = int(agent_input.context["goal"]["daily_minutes"])
        durations = self._durations(agent_input.pace_factors, daily_minutes)
        if daily_minutes < durations["diagnostic"]:
            raise ValueError(f"daily_minutes must be at least {self.DIAGNOSTIC_MINUTES}")

        states, deferred_states, review_states = self._states(agent_input.workloads)
        days: list[dict[str, Any]] = []
        for index in range(agent_input.plan_days):
            scheduled = agent_input.start_date + timedelta(days=index)
            capacity = daily_minutes - durations["diagnostic"]
            # A review date is a scheduling constraint, not merely a value kept
            # in the learner model.  Put due retrieval practice ahead of newly
            # introduced material, then use the remaining daily budget for the
            # BKT-driven learning sequence.
            review_items = self._build_due_review_items(review_states, scheduled, capacity, durations)
            capacity -= sum(int(item["minutes"]) for item in review_items)
            learning_items = [*review_items, *self._build_day_learning_items(states, capacity, durations)]
            focus = learning_items[0] if learning_items else self._next_focus(states)
            days.append(self._day(scheduled, index, focus, learning_items, durations))

        deferred = sorted(
            {
                *(
                    int(state["knowledge_point_id"])
                    for state in states
                    if bool(state["reading_pending"]) or int(state["practice_remaining"]) > 0
                ),
                *(int(state["knowledge_point_id"]) for state in deferred_states),
            }
        )
        return {"days": days, "deferred_knowledge_point_ids": deferred}

    def _durations(self, factors: dict[str, float], daily_minutes: int) -> dict[str, int]:
        baseline = {"reading": self.READING_MINUTES, "practice": self.PRACTICE_MINUTES, "review": self.PRACTICE_MINUTES, "diagnostic": self.DIAGNOSTIC_MINUTES}
        durations = {key: max(1, round(value * max(0.6, min(2.0, float(factors.get(key, 1.0)))))) for key, value in baseline.items()}
        durations["diagnostic"] = min(durations["diagnostic"], daily_minutes)
        return durations

    def _states(self, workloads: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]] , list[dict[str, Any]]]:
        states: list[dict[str, Any]] = []
        review_states: list[dict[str, Any]] = []
        for workload in sorted(workloads, key=lambda item: (-float(item["priority_score"]), int(item["course_order"]))):
            opportunities = max(0, int(workload["expected_practice_count"]))
            if workload.get("next_review_at"):
                review_states.append({
                    **workload,
                    "review_scheduled": False,
                })
            if opportunities <= 0:
                continue
            states.append({
                **workload,
                "reading_pending": True,
                "practice_remaining": opportunities,
                "next_practice_sequence": 1,
                "review_scheduled": False,
            })
        # A seven-day window should develop a small group of high-gap points,
        # rather than opening every weak point once and leaving no time for
        # retrieval practice.  Priority already incorporates mastery gap and
        # evidence confidence; course order breaks ties deterministically.
        return states[:self.MAX_ACTIVE_KNOWLEDGE_POINTS], states[self.MAX_ACTIVE_KNOWLEDGE_POINTS:], review_states

    def _build_due_review_items(self, states: list[dict[str, Any]], scheduled: date, capacity: int, durations: dict[str, int]) -> list[dict[str, Any]]:
        """Reserve time for each knowledge point whose spaced review is due."""

        items: list[dict[str, Any]] = []
        due_states = sorted(
            (
                state
                for state in states
                if not bool(state["review_scheduled"])
                and self._review_due_on_or_before(state.get("next_review_at"), scheduled)
            ),
            key=lambda state: (-float(state["priority_score"]), int(state["course_order"])),
        )
        for state in due_states:
            if capacity < durations["review"]:
                break
            items.append(self._review_item(state, durations["review"]))
            state["review_scheduled"] = True
            capacity -= durations["review"]
        return items

    @staticmethod
    def _review_due_on_or_before(next_review_at: Any, scheduled: date) -> bool:
        if not next_review_at:
            return False
        if isinstance(next_review_at, datetime):
            return next_review_at.date() <= scheduled
        if isinstance(next_review_at, date):
            return next_review_at <= scheduled
        try:
            return datetime.fromisoformat(str(next_review_at).replace("Z", "+00:00")).date() <= scheduled
        except ValueError:
            return False

    def _build_day_learning_items(self, states: list[dict[str, Any]], capacity: int, durations: dict[str, int]) -> list[dict[str, Any]]:
        """Schedule prerequisite reading, then at most one practice per point."""

        items: list[dict[str, Any]] = []
        practiced_today: set[int] = set()
        while capacity >= durations["practice"]:
            state = self._next_reading(states, capacity, durations["reading"])
            if state is not None:
                items.append(self._reading_item(state, durations["reading"]))
                state["reading_pending"] = False
                capacity -= durations["reading"]
                if capacity >= durations["practice"] and int(state["practice_remaining"]) > 0:
                    items.append(self._practice_item(state, durations["practice"]))
                    practiced_today.add(int(state["knowledge_point_id"]))
                    capacity -= durations["practice"]
                continue

            state = self._next_practice(states, practiced_today)
            if state is None:
                break
            items.append(self._practice_item(state, durations["practice"]))
            practiced_today.add(int(state["knowledge_point_id"]))
            capacity -= durations["practice"]
        return items

    @staticmethod
    def _next_reading(states: list[dict[str, Any]], capacity: int, reading_minutes: int) -> dict[str, Any] | None:
        if capacity < reading_minutes:
            return None
        return next((state for state in states if bool(state["reading_pending"])), None)

    @staticmethod
    def _next_practice(states: list[dict[str, Any]], practiced_today: set[int]) -> dict[str, Any] | None:
        return next((state for state in states if not bool(state["reading_pending"]) and int(state["practice_remaining"]) > 0 and int(state["knowledge_point_id"]) not in practiced_today), None)

    @staticmethod
    def _next_focus(states: list[dict[str, Any]]) -> dict[str, Any] | None:
        return next((state for state in states if bool(state["reading_pending"]) or int(state["practice_remaining"]) > 0), None)

    def _day(self, scheduled: date, index: int, focus: dict[str, Any] | None, learning_items: list[dict[str, Any]], durations: dict[str, int]) -> dict[str, Any]:
        focus_name = str((focus or {}).get("knowledge_point_name") or "本日复习")
        diagnostic = {
            "title": f"学习前诊断：{focus_name}（{durations['diagnostic']}分钟）",
            "description": f"先完成 {durations['diagnostic']} 分钟诊断题，校准今日后续任务难度。",
            "source": "review_due",
            "adaptive_reason": "围绕当天实际学习主题进行诊断，用于滚动更新掌握度与计划。",
            "knowledge_point_id": int((focus or {}).get("knowledge_point_id") or 0),
            "minutes": durations["diagnostic"],
            "priority_score": float((focus or {}).get("priority_score") or 0),
        }
        items = [diagnostic, *learning_items]
        return {
            "date": scheduled.isoformat(),
            "title": f"第 {index + 1} 天学习计划",
            "adaptive_reason": "根据当前掌握度、目标掌握度和 BKT 预计练习次数生成，并遵守阅读先行与每日练习上限。",
            "priority_score": round(max((float(item.get("priority_score", 0)) for item in items), default=0.0), 4),
            "planned_minutes": sum(int(item["minutes"]) for item in items),
            "knowledge_point_ids": sorted({int(item["knowledge_point_id"]) for item in items if int(item["knowledge_point_id"])}),
            "items": items,
        }

    def _reading_item(self, state: dict[str, Any], minutes: int) -> dict[str, Any]:
        point_name = str(state["knowledge_point_name"])
        return {
            "title": f"阅读：{state.get('chapter_title') or '所属章节'}—{point_name}（{minutes}分钟）",
            "description": f"阅读“{point_name}”对应章节内容，整理关键概念与例子。",
            "source": "weak_point",
            "adaptive_reason": "该知识点尚未完成阅读，先建立概念框架后再练习。",
            "knowledge_point_id": int(state["knowledge_point_id"]),
            "knowledge_point_name": point_name,
            "minutes": minutes,
            "priority_score": float(state["priority_score"]),
        }

    def _practice_item(self, state: dict[str, Any], minutes: int) -> dict[str, Any]:
        sequence = int(state["next_practice_sequence"])
        question_ids = state.get("question_ids") or []
        question_id = question_ids[(sequence - 1) % len(question_ids)] if question_ids else None
        reference = f"，优先题目 #{question_id}" if question_id else ""
        state["practice_remaining"] = int(state["practice_remaining"]) - 1
        state["next_practice_sequence"] = sequence + 1
        point_name = str(state["knowledge_point_name"])
        return {
            "title": f"练习：{point_name}（第 {sequence} 次，{minutes}分钟）",
            "description": f"完成一次围绕“{point_name}”的有效练习{reference}，记录错因并查看反馈。",
            "source": "weak_point",
            "adaptive_reason": "BKT 预计仍需有效练习；同一知识点每天最多安排一次。",
            "knowledge_point_id": int(state["knowledge_point_id"]),
            "knowledge_point_name": point_name,
            "minutes": minutes,
            "priority_score": float(state["priority_score"]),
        }

    def _review_item(self, state: dict[str, Any], minutes: int) -> dict[str, Any]:
        """Create a retrieval-practice task without consuming BKT new-practice demand."""

        question_ids = state.get("question_ids") or []
        question_id = question_ids[0] if question_ids else None
        reference = f"，优先题目 #{question_id}" if question_id else ""
        point_name = str(state["knowledge_point_name"])
        return {
            "title": f"复习：{point_name}（{minutes}分钟）",
            "description": f"根据遗忘间隔完成一次检索复习{reference}，重点回忆核心概念并记录错误。",
            "source": "spaced_review",
            "adaptive_reason": f"该知识点的下次复习时间已到（{state.get('next_review_at')}），优先安排巩固。",
            "knowledge_point_id": int(state["knowledge_point_id"]),
            "knowledge_point_name": point_name,
            "minutes": minutes,
            "priority_score": float(state["priority_score"]),
        }
