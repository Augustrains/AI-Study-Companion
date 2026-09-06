"""Deterministic seven-day planning agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import json
from typing import Any


@dataclass(frozen=True)
class WeeklyPlanningInput:
    context: dict[str, Any]
    workloads: list[dict[str, Any]]
    start_date: date
    plan_days: int = 7
    pace_factors: dict[str, float] = field(default_factory=dict)
    regeneration_reason: str = ""


class WeeklyLearningPlanAgent:
    """Turn BKT opportunities into a paced, prerequisite-safe study plan."""

    READING_MINUTES = 15
    PRACTICE_MINUTES = 3
    DIAGNOSTIC_MINUTES = 10
    PLAN_DAYS = 7
    MAX_ACTIVE_KNOWLEDGE_POINTS = 3

    def __init__(self, llm_client: Any | None = None) -> None:
        self.llm_client = llm_client

    def build_weekly_outline(self, agent_input: WeeklyPlanningInput) -> dict[str, Any]:
        """Create the seven-day *skeleton*, without committing future tasks.

        A week plan communicates the intended focus and priority.  Concrete
        reading/practice tasks are deliberately deferred until that date's
        diagnostic has supplied fresh evidence.
        """

        states, _deferred, _reviews = self._states(agent_input.workloads)
        focuses = states or sorted(
            agent_input.workloads,
            key=lambda item: (-float(item.get("priority_score", 0)), int(item.get("course_order", 0))),
        )
        days: list[dict[str, Any]] = []
        for index in range(agent_input.plan_days):
            focus = focuses[index % len(focuses)] if focuses else None
            name = str((focus or {}).get("knowledge_point_name") or "动态复习")
            days.append(
                {
                    "date": (agent_input.start_date + timedelta(days=index)).isoformat(),
                    "title": f"第 {index + 1} 天 · 聚焦{name}",
                    "adaptive_reason": "周计划仅确定学习重点；当天诊断完成后再动态生成具体任务。",
                    "priority_score": round(float((focus or {}).get("priority_score") or 0), 4),
                    "items": [],
                }
            )
        return {"days": days, "deferred_knowledge_point_ids": []}

    def build_daily_diagnostic(self, *, context: dict[str, Any], workloads: list[dict[str, Any]], scheduled: date) -> dict[str, Any]:
        """Create only the first task of a day: its evidence-gathering diagnostic."""

        durations = self._durations({}, int(context["goal"]["daily_minutes"]))
        states, _deferred, _reviews = self._states(workloads)
        focus = self._next_focus(states)
        return self._day(scheduled, 0, focus, [], durations)

    def build_daily_learning(self, *, context: dict[str, Any], workloads: list[dict[str, Any]], scheduled: date, pace_factors: dict[str, float] | None = None) -> dict[str, Any]:
        """Generate today's post-diagnostic learning tasks from fresh mastery."""

        daily_minutes = int(context["goal"]["daily_minutes"])
        durations = self._durations(pace_factors or {}, daily_minutes)
        states, _deferred, review_states = self._states(workloads)
        capacity = daily_minutes - durations["diagnostic"]
        review_items = self._build_due_review_items(review_states, scheduled, capacity, durations)
        capacity -= sum(int(item["minutes"]) for item in review_items)
        learning_items = [*review_items, *self._build_day_learning_items(states, capacity, durations)]
        return self._day(scheduled, 0, self._next_focus(states), learning_items, durations)

    def build(self, agent_input: WeeklyPlanningInput) -> dict[str, Any]:
        daily_minutes = int(agent_input.context["goal"]["daily_minutes"])
        durations = self._durations(agent_input.pace_factors, daily_minutes)
        if daily_minutes < durations["diagnostic"]:
            raise ValueError(f"daily_minutes must be at least {self.DIAGNOSTIC_MINUTES}")

        workloads = self._apply_user_focus(agent_input.workloads, agent_input.regeneration_reason)
        states, deferred_states, review_states = self._states(workloads)
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
            requested_focus = next((state for state in states if state.get("user_requested_focus")), None)
            focus = requested_focus or (learning_items[0] if learning_items else self._next_focus(states))
            days.append(self._day(scheduled, index, focus, learning_items, durations, agent_input.regeneration_reason))

        self._apply_agent_reasons(days, agent_input)
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
        reading_titles = []
        for day in days:
            for item in day["items"]:
                if str(item.get("title", "")).startswith("阅读：") and item["title"] not in reading_titles:
                    reading_titles.append(item["title"])
        resources = [{"id": f"plan-reading-{index}", "type": "教材", "title": title.removeprefix("阅读："), "location": "对应教材章节", "excerpt": "本周计划中的重点阅读材料。"} for index, title in enumerate(reading_titles[:5], start=1)]
        focus = str((days[0].get("title") if days else "当前重点知识点")).replace("第 1 天学习计划", "").strip()
        advice = [f"建议每天先完成诊断，再按“阅读—复习—练习”的顺序学习；本周优先巩固{focus}。"]
        return {"days": days, "deferred_knowledge_point_ids": deferred, "advice": advice, "resources": resources}

    @staticmethod
    def _apply_user_focus(workloads: list[dict[str, Any]], reason: str) -> list[dict[str, Any]]:
        """Turn an explicit regeneration request into a scheduling priority."""
        query = (reason or "").strip().lower()
        if not query:
            return workloads
        aliases = {"k-means": ("kmeans", "k-means", "均值聚类", "聚类"), "kmeans": ("kmeans", "k-means", "均值聚类", "聚类"), "回归": ("回归", "regression"), "分类": ("分类", "classification")}
        terms = {query, *[alias for key, values in aliases.items() if key in query for alias in values]}
        adjusted: list[dict[str, Any]] = []
        for workload in workloads:
            searchable = " ".join(str(workload.get(key) or "") for key in ("knowledge_point_name", "knowledge_point_code", "description", "chapter_title")).lower()
            matched = any(term and term in searchable for term in terms)
            adjusted.append({**workload, "priority_score": float(workload.get("priority_score") or 0) + (100.0 if matched else 0.0), "user_requested_focus": matched})
        return adjusted

    def _apply_agent_reasons(self, days: list[dict[str, Any]], agent_input: WeeklyPlanningInput) -> None:
        if self.llm_client is None or not days:
            return
        brief = [{"day": index + 1, "date": day["date"], "focus": day["title"], "tasks": [item["title"] for item in day["items"]]} for index, day in enumerate(days)]
        prompt = (
            "你是自适应学习计划 Agent。请为下面每一天生成一条简洁、具体的中文计划理由。"
            "理由必须解释当天为什么安排这些任务，引用当天知识点、诊断、复习、阅读或练习等事实；"
            "不要写泛泛的固定模板，不要重复同一句，不要输出学习目标或额外建议。只输出 JSON 数组，"
            "格式为 [{\"day\":1,\"reason\":\"...\"}]。用户重新生成原因："
            f"{agent_input.regeneration_reason or '无'}\n计划：{json.dumps(brief, ensure_ascii=False)}"
        )
        try:
            raw = self.llm_client.generate(prompt).strip()
            payload = json.loads(raw.strip().removeprefix("``json").removesuffix("``").strip())
            reasons = {int(item["day"]): str(item["reason"]).strip() for item in payload if isinstance(item, dict) and item.get("day") and item.get("reason")}
            for index, day in enumerate(days, start=1):
                if reasons.get(index):
                    day["adaptive_reason"] = reasons[index]
        except Exception:
            # Rule-based explanations remain available when the model is down.
            return

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

    def _day(self, scheduled: date, index: int, focus: dict[str, Any] | None, learning_items: list[dict[str, Any]], durations: dict[str, int], regeneration_reason: str = "") -> dict[str, Any]:
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
        reason = self._day_reason(focus_name, learning_items, regeneration_reason)
        return {
            "date": scheduled.isoformat(),
            "title": f"第 {index + 1} 天学习计划",
            "adaptive_reason": reason,
            "priority_score": round(max((float(item.get("priority_score", 0)) for item in items), default=0.0), 4),
            "planned_minutes": sum(int(item["minutes"]) for item in items),
            "knowledge_point_ids": sorted({int(item["knowledge_point_id"]) for item in items if int(item["knowledge_point_id"])}),
            "items": items,
        }

    @staticmethod
    def _day_reason(focus_name: str, learning_items: list[dict[str, Any]], regeneration_reason: str = "") -> str:
        """Explain the concrete evidence behind this day's schedule."""
        titles = [str(item.get("title") or "") for item in learning_items]
        has_reading = any(title.startswith("阅读：") for title in titles)
        review_count = sum(title.startswith(("复习：", "检索：")) for title in titles)
        practice_count = sum(title.startswith("练习：") for title in titles)
        clauses = [f"当天先诊断“{focus_name}”，用于校准开始学习前的掌握度"]
        if has_reading:
            clauses.append("薄弱知识点先阅读建立概念框架")
        if review_count:
            clauses.append(f"安排 {review_count} 项历史到期内容进行间隔复习")
        if practice_count:
            clauses.append(f"再安排 {practice_count} 次针对性练习")
        if not learning_items:
            clauses.append("后续任务将依据诊断结果动态调整")
        if regeneration_reason.strip():
            clauses.append(f"本次重排参考：{regeneration_reason.strip()}")
        return "；".join(clauses) + "。"

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
