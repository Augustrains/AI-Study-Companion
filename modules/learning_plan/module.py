"""学习计划领域模块。

负责校验诊断会话状态、生成学习任务，并调用代理生成建议与资源。
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from modules.common.errors import ValidationAppError
from modules.diagnosis.services import DiagnosisResultStore
from modules.diagnosis.models import STATUSES
from modules.common import api as common_api

from .agent import LearningPlanAgent, LearningPlanAgentInput
from .models import LEARNING_TASK_TYPES_BY_SOURCE, LearningTask

if False:  # pragma: no cover
    from modules.learner_profile.workflow import LearnerProfileWorkflow
    from modules.learner_goals.module import LearnerGoalModule
    from modules.learning_record.module import LearningRecordModule
    from modules.memory.module import MemoryModule


# 前端使用的教材编号与诊断题库编号之间的映射。
BOOK_TO_QUESTION_BANK = {"ml": "ml-001", "dl": "dl-001"}

# 诊断结果中的知识点编号到用户可读名称的映射。
KNOWLEDGE_POINT_NAMES = {
    "supervised_learning": "监督学习",
    "linear_regression": "线性回归",
    "model_evaluation": "模型评估",
    "overfitting": "过拟合与泛化",
    "deep_learning": "深度学习基础",
    "neural_network": "神经网络",
    "backpropagation": "反向传播",
    "convolution": "卷积网络",
}


class LearningPlanModule:
    """从已完成的诊断会话生成前端学习任务。"""

    DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "learning_plan" / "plans.json"

    def __init__(self, results: DiagnosisResultStore, agent: LearningPlanAgent | None = None, path: str | Path | None = None, memory: "MemoryModule | None" = None, learner_profile: "LearnerProfileWorkflow | None" = None, learner_goals: "LearnerGoalModule | None" = None, learning_record: "LearningRecordModule | None" = None) -> None:
        """保存诊断会话存储，并允许注入自定义计划生成代理。

        learner_goals 提供用户设定的每周投入时长，用于把任务按天摊开；
        没注入或用户没设过目标时，排课退回原来的行为（不做时间约束）。
        learning_record 提供历史「计划用时 vs 实际用时」，用于校准排课节奏；
        没注入或样本不足时校准倍数为 1.0（等于不校准）。
        """
        self.results = results
        self.agent = agent or LearningPlanAgent()
        target = path or self.DEFAULT_PATH
        self.reader = common_api.json_storage.JsonContentReader(target)
        self.store = common_api.json_storage.JsonStore()
        self.memory = memory
        self.learner_profile = learner_profile
        self.learner_goals = learner_goals
        self.learning_record = learning_record

    def get_saved(self, *, book_id: str, diagnostic_id: str | None = None, user_id: str = "") -> dict[str, Any] | None:
        """读取某本书的在途计划。

        user_id 非空时按用户过滤：计划文件是全用户共用一个 plans.json，
        不过滤的话 A 用户会读到 B 用户的计划。
        没有 userId 字段的历史计划一律不匹配——宁可让用户重新生成一份，
        也不猜它属于谁。
        """
        payload = self.reader.read(allow_missing=True, allow_empty=False)
        if payload == {}:
            return None
        if not isinstance(payload, dict):
            raise common_api.errors.StorageReadError("learning plan resource must be a JSON object")
        candidates = [item for item in payload.values() if isinstance(item, dict) and item.get("bookId") == book_id and item.get("status") != "completed"]
        if user_id:
            candidates = [item for item in candidates if item.get("userId") == user_id]
        if diagnostic_id:
            candidates = [item for item in candidates if item.get("diagnosticId") == diagnostic_id]
        if not candidates:
            return None
        plan = candidates[-1].get("plan")
        if not isinstance(plan, dict):
            return plan
        # 兼容 source/type 尚未加入前生成的历史计划。
        normalized = dict(plan)
        normalized["tasks"] = [
            self._normalize_task(item, candidates[-1])
            for item in plan.get("tasks", [])
            if isinstance(item, dict)
        ]
        return normalized

    @staticmethod
    def _normalize_task(task: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(task)
        legacy_types = {
            "能力强化": "concept_review",
            "能力练习": "practice",
            "资料问答": "qa_review",
        }
        normalized["type"] = legacy_types.get(str(normalized.get("type", "")), normalized.get("type", ""))
        if not normalized.get("source"):
            normalized["source"] = "diagnostic" if record.get("diagnosticId") else "material_qa"
        return normalized

    def create_task_plan(
        self,
        *,
        book_id: str,
        task: dict[str, Any],
        goal: str,
        goal_level: str,
        advice: list[str] | None = None,
        resources: list[dict[str, Any]] | None = None,
        plan_key: str | None = None,
        diagnostic_id: str = "",
        user_id: str = "",
    ) -> dict[str, Any]:
        """Create/extend a plan and persist it through the shared plan store.

        Both diagnostic-generated tasks and material-QA tasks use this entry
        point so task shape and local persistence stay consistent.
        """
        existing = self.get_saved(book_id=book_id, diagnostic_id=diagnostic_id or None, user_id=user_id)
        if existing is None:
            plan = {
                "book": self._book(book_id),
                "goal": goal,
                "goalLevel": goal_level,
                "tasks": [task],
                "advice": advice or [],
                "resources": resources or [],
            }
        else:
            plan = dict(existing)
            plan["tasks"] = [*existing.get("tasks", []), task]
            plan["resources"] = self._merge_resources(existing.get("resources", []), resources or [])
            plan["advice"] = list(dict.fromkeys([*existing.get("advice", []), *(advice or [])]))
        key = plan_key or f"{book_id}:{diagnostic_id or 'material'}:{task['id']}"
        self.persist_plan(
            book_id=book_id,
            diagnostic_id=diagnostic_id,
            plan=plan,
            plan_key=key,
            user_id=user_id,
        )
        return plan

    def persist_plan(
        self,
        *,
        book_id: str,
        diagnostic_id: str,
        plan: dict[str, Any],
        plan_key: str,
        user_id: str = "",
    ) -> dict[str, Any]:
        """Persist any plan shape through the single local storage gateway."""
        self.store.save(
            path=self.reader.path,
            content={"bookId": book_id, "diagnosticId": diagnostic_id, "userId": user_id, "plan": plan},
            mode="upsert",
            key_path=[plan_key],
        )
        return plan

    def complete_task(self, *, user_id: str, task_id: str, plan_id: str = "", book_id: str = "") -> dict[str, Any]:
        """Complete a server-owned task, update its plan, and update memory."""
        payload = self.reader.read(allow_missing=True, allow_empty=False)
        if not isinstance(payload, dict):
            raise common_api.errors.StorageReadError("learning plan resource must be a JSON object")
        match_key = None
        match_record = None
        match_task = None
        for key, record in payload.items():
            if not isinstance(record, dict) or (book_id and record.get("bookId") != book_id):
                continue
            if plan_id and key != plan_id and record.get("planId") != plan_id and record.get("diagnosticId") != plan_id:
                continue
            plan = record.get("plan")
            if not isinstance(plan, dict):
                continue
            task = next((item for item in plan.get("tasks", []) if isinstance(item, dict) and item.get("id") == task_id), None)
            if task is not None:
                match_key, match_record, match_task = key, record, task
                break
        if match_record is None or match_task is None:
            raise ValidationAppError("learning task not found", details={"task_id": task_id})

        plan = dict(match_record["plan"])
        tasks = [dict(item) for item in plan.get("tasks", [])]
        was_completed = bool(match_task.get("status") == "completed")
        for task in tasks:
            if task.get("id") == task_id:
                task["status"] = "completed"
        all_completed = bool(tasks) and all(item.get("status") == "completed" for item in tasks)
        plan["tasks"] = tasks
        if all_completed:
            plan["status"] = "completed"
            match_record = {**match_record, "status": "completed"}
        else:
            match_record = {**match_record, "plan": plan}
        match_record["plan"] = plan
        self.store.save(path=self.reader.path, content=match_record, mode="upsert", key_path=[match_key])

        memories = []
        if self.memory and match_record.get("bookId") and not was_completed:
            learning_domain = {"ml": "ml-001", "dl": "dl-001"}.get(
                str(match_record["bookId"]), str(match_record["bookId"])
            )
            memories = self.memory.ingest_task_completion(
                user_id=user_id,
                learning_domain=learning_domain,
                task_id=task_id,
                knowledge_point_ids=list(
                    match_task.get("knowledgePointIds")
                    or match_task.get("knowledge_point_ids")
                    or []
                ),
            )
        return {
            "plan": plan,
            "planCompleted": all_completed,
            "memoryUpdated": bool(memories),
            "bookId": match_record.get("bookId", ""),
            "planId": match_key,
            "knowledgePointIds": list(
                match_task.get("knowledgePointIds")
                or match_task.get("knowledge_point_ids")
                or []
            ),
            "alreadyCompleted": was_completed,
        }

    def generate(self, *, diagnostic_id: str, book_id: str, goal: str, user_id: str = "") -> dict[str, Any]:
        """校验输入后，生成任务、学习建议及相关资源。"""
        diagnosis = self.results.get(diagnostic_id)
        # 只允许为自己的诊断生成计划。user_id 为空表示调用方没传（旧客户端），
        # 保持原行为不阻断；传了就必须对得上。
        if user_id and diagnosis.user_id != user_id:
            raise ValidationAppError(
                "diagnostic session belongs to another user",
                details={"diagnostic_id": diagnostic_id},
            )
        # 兼容前端教材编号和后端题库编号，防止跨教材生成计划。
        expected_book_id = BOOK_TO_QUESTION_BANK.get(book_id, book_id)
        if diagnosis.book_id != expected_book_id:
            raise ValidationAppError(
                "diagnostic session does not belong to the requested book",
                details={"diagnostic_id": diagnostic_id, "book_id": book_id},
            )
        result_payload = common_api.serialization.to_data(diagnosis)
        #从已完成的诊断会话读取用户答题结果
        results = result_payload.get("results", [])
        answer_result = result_payload["answer_result"]
        nested_records = answer_result["answer_records"]
        questions = [item["question"] for item in nested_records]
        answer_records = [
            {
                "question_id": item["question"]["id"],
                "knowledge_point_ids": item["question"].get("knowledge_point_ids", []),
                "submitted_answer": item["submitted_answer"],
                "correct_answer": item["correct_answer"],
                "is_correct": item["is_correct"],
                "skipped": item["skipped"],
                "hint_count": item["hint_count"],
                "retry_count": item["retry_count"],
                "is_independent": item["is_independent"],
            }
            for item in nested_records
        ]
        # 诊断按知识点统计，计划按能力聚合；知识点和章节作为任务证据保留。
        planning_units = self._build_planning_units(questions, answer_records, results)
        #按照能力掌握排序
        ordered_results = sorted(planning_units, key=self._status_rank)
        question_evidence = self._build_question_evidence(questions, answer_records)
        learner_preferences = self._learner_preferences(diagnosis.user_id, diagnosis.book_id)
        session_budget = learner_preferences.get("sessionTimeBudgetMinutes")
        fallback_tasks = [
            self._build_task(diagnostic_id, item, index, goal, session_budget)
            for index, item in enumerate(ordered_results)
        ]
        daily_budget = self._daily_minutes_budget(diagnosis.user_id, book_id)
        agent_input = LearningPlanAgentInput(
            book=self._book(book_id),
            goal=goal,
            goal_level=self._goal_level(results),
            diagnostic_summary=self._diagnostic_summary(question_evidence),
            knowledge_point_results=self._knowledge_point_contexts(results, answer_records),
            ability_units=ordered_results,
            question_evidence=question_evidence,
            candidate_resources=self._resource_candidates(book_id, questions, results),
            calibration={
                "adjustment": diagnosis.calibration,
                "reason": diagnosis.calibration_reason,
            },
            learner_preferences=learner_preferences,
            constraints={
                "allowedTaskTypes": list(LEARNING_TASK_TYPES_BY_SOURCE["diagnostic"]),
                "minTaskCount": len(ordered_results),
                "maxTaskCount": len(ordered_results),
                "minTaskMinutes": 5,
                "maxTaskMinutes": self._max_task_minutes(session_budget),
                # 用户在「选书与目标」里设定的每周时长折算成的每日分钟预算；
                # None 表示没设过目标，模型不必考虑时间约束。
                "dailyMinutesBudget": daily_budget,
            },
        )
        plan = self.agent.build(agent_input, fallback_tasks=fallback_tasks)
        plan = self._apply_time_budget(
            plan,
            daily_budget=daily_budget,
            pace_factor=self.pace_factor(diagnosis.user_id, book_id),
        )
        self.persist_plan(
            book_id=book_id,
            diagnostic_id=diagnostic_id,
            plan=plan,
            plan_key=f"{book_id}:{diagnostic_id}",
            # 计划归属跟随诊断，而不是请求参数——诊断是谁做的，计划就是谁的。
            user_id=diagnosis.user_id,
        )
        return plan

    # ---------- 实际速度校准 ----------

    # 至少要有这么多条完成记录才敢用实际速度校准，样本太少就是噪声。
    PACE_MIN_SAMPLES = 3
    # 只看最近这些条，速度会随熟练度变化，太老的记录不代表现在。
    PACE_WINDOW = 10
    # 校准倍数的上下限。一次误填的 24 小时不该把后面的排课全毁掉。
    PACE_MIN, PACE_MAX = 0.5, 3.0
    # 在这个区间内视为「估得挺准」，不做校准也不提示。
    PACE_NEUTRAL = (0.9, 1.1)

    def pace_factor(self, user_id: str, book_id: str) -> float:
        """用户实际用时相对于计划用时的倍数。1.0 表示估得准，2.0 表示总要花两倍时间。

        取最近若干条完成记录里「实际 / 计划」的**中位数**，而不是总和之比：
        总和之比会被一两个特别长的任务主导，中位数对误填和偶发的通宵更稳。
        样本不足、没有学习记录模块、或者算不出来时一律返回 1.0（不校准）。
        """

        if self.learning_record is None:
            return 1.0
        try:
            page = self.learning_record.list_activities(
                user_id,
                category="task",
                activity_type="task_completed",
                page=1,
                page_size=50,
            )
        except Exception:  # noqa: BLE001 - 读不到记录就是不校准，不该影响生成计划
            return 1.0

        expected = {book_id, BOOK_TO_QUESTION_BANK.get(book_id, book_id)}
        ratios: list[float] = []
        for activity in page.get("records", []):
            if getattr(activity, "book_id", "") and activity.book_id not in expected:
                continue
            result = getattr(activity, "result", {}) or {}
            planned = int(result.get("planned_minutes", 0) or 0)
            actual_seconds = int(result.get("duration_seconds", 0) or 0)
            if planned <= 0 or actual_seconds <= 0:
                # 计划分钟数缺失的历史记录没法算比值，跳过而不是当成 1.0。
                continue
            ratios.append((actual_seconds / 60) / planned)
            if len(ratios) >= self.PACE_WINDOW:
                break

        if len(ratios) < self.PACE_MIN_SAMPLES:
            return 1.0
        ratios.sort()
        middle = len(ratios) // 2
        median = ratios[middle] if len(ratios) % 2 else (ratios[middle - 1] + ratios[middle]) / 2
        return round(min(self.PACE_MAX, max(self.PACE_MIN, median)), 2)

    # ---------- 每周时长 → 每日排课 ----------

    def _daily_minutes_budget(self, user_id: str, book_id: str) -> int | None:
        """用户设定的每周时长折算成每天分钟数；没设过目标返回 None。"""
        if self.learner_goals is None:
            return None
        try:
            return self.learner_goals.daily_minutes_budget(user_id=user_id, book_id=book_id)
        except Exception:  # noqa: BLE001 - 目标读不出来不该让计划生成失败
            return None

    # 单个任务的绝对上限：2 小时。再长的一次性学习任务不现实，应该拆成两个。
    MAX_TASK_MINUTES = 120
    DEFAULT_TASK_MINUTES = 30

    @staticmethod
    def _max_task_minutes(session_budget: Any, daily_budget: int | None = None) -> int:
        """单个任务的时长上限，由用户的「单次学习时长」偏好决定。

        改动说明：原来这里写死上限 60，并且还拿每日预算再压一次。
        结果是每周时长填得少的人，任务被压到二三十分钟——用户反馈「学不了那么快」，
        想按一小时以上排课时根本排不出来。

        现在只看单次时长偏好（15/30/45/60/90/120，用户在学习画像里选），
        **不再用每日预算封顶**：每日预算决定任务摊几天做完，不决定一次坐下来学多久。
        一个 120 分钟的任务遇上 40 分钟的日预算，会由 _apply_time_budget 独占一天，
        而不是被砍成 40 分钟——砍短了任务就不完整了。

        daily_budget 参数保留只为兼容既有调用，不再参与计算。
        """
        limit = int(session_budget) if session_budget else LearningPlanModule.DEFAULT_TASK_MINUTES
        return max(5, min(LearningPlanModule.MAX_TASK_MINUTES, limit))

    @staticmethod
    def _apply_time_budget(
        plan: dict[str, Any],
        *,
        daily_budget: int | None,
        pace_factor: float = 1.0,
        only_unfinished: bool = False,
    ) -> dict[str, Any]:
        """按每日分钟预算把任务顺序摊到具体日期上。

        这是 weeklyHours 真正起作用的地方：以前它只是被保存下来，排出来的
        计划和填 3 小时还是 15 小时没有任何区别。

        做法是顺序装箱——任务保持原有优先级顺序，累计时长超过当天预算就开新的一天，
        并把 expectedCompletionDate 写成对应日期。**不删任务、不压缩时长**：
        计划的内容由诊断结果决定，时间预算只决定它摊多少天完成。
        超长的单个任务（本身就超过一天预算）独占一天，不会被切碎。

        pace_factor 是用户的实际速度校准：装箱时用 `minutes × pace_factor`
        计算占用，但**任务自己的 minutes 保持 AI 的原始估计不变**。
        这一点是刻意的——如果把校准值写回 minutes，下一轮算「计划 vs 实际」
        的比值就会自动趋近 1，校准会把自己的输入抹掉，越校越准是假象。

        only_unfinished=True 时只重排还没完成的任务，已完成任务的日期冻结在原处
        （那是历史，不该因为改了目标就被改写）。
        """
        tasks = plan.get("tasks")
        if not daily_budget or not isinstance(tasks, list) or not tasks:
            return plan

        factor = max(0.1, float(pace_factor or 1.0))
        today = date.today()
        day_index = 0
        used = 0.0
        scheduled: list[dict[str, Any]] = []
        for item in tasks:
            if not isinstance(item, dict):
                scheduled.append(item)
                continue
            if only_unfinished and str(item.get("status", "")) == "completed":
                scheduled.append(item)
                continue
            minutes = int(item.get("minutes", 0) or 0)
            occupied = minutes * factor
            if used and used + occupied > daily_budget:
                day_index += 1
                used = 0.0
            used += occupied
            task = dict(item)
            task["expectedCompletionDate"] = (today + timedelta(days=day_index)).isoformat()
            scheduled.append(task)

        planned_total = sum(
            int(item.get("minutes", 0) or 0)
            for item in scheduled
            if isinstance(item, dict) and not (only_unfinished and str(item.get("status", "")) == "completed")
        )
        days = day_index + 1
        updated = dict(plan)
        updated["tasks"] = scheduled
        updated["timeBudget"] = {
            "dailyMinutes": daily_budget,
            "totalMinutes": planned_total,
            "estimatedDays": days,
            "paceFactor": round(factor, 2),
            # 按实际速度折算出来的总时长，前端用它说「预计实际要花多久」。
            "adjustedTotalMinutes": int(round(planned_total * factor)),
        }
        advice = [item for item in (updated.get("advice") or []) if not str(item).startswith(LearningPlanModule.SCHEDULE_ADVICE_PREFIX)]
        advice.append(LearningPlanModule._schedule_advice(daily_budget, planned_total, days, factor))
        updated["advice"] = list(dict.fromkeys(advice))
        return updated

    # 排课说明每次重排都会重写，用固定前缀标识，避免重排一次追加一条。
    SCHEDULE_ADVICE_PREFIX = "按你设定的每天约"

    @staticmethod
    def _schedule_advice(daily_budget: int, planned_total: int, days: int, factor: float) -> str:
        low, high = LearningPlanModule.PACE_NEUTRAL
        base = (
            f"{LearningPlanModule.SCHEDULE_ADVICE_PREFIX} {daily_budget} 分钟，"
            f"这份计划共 {planned_total} 分钟，预计 {days} 天完成"
        )
        if low <= factor <= high:
            return base + "；想更快就回到「选书与目标」调高每周时长。"
        if factor > high:
            return (
                base
                + f"。已按你最近的实际速度（约为计划用时的 {factor} 倍）放慢排课，"
                "所以每天排的任务比原估计少。"
            )
        return (
            base
            + f"。你最近实际用时约为计划的 {factor} 倍，比估计快，已相应多排了一些。"
        )

    def reschedule(self, *, user_id: str, book_id: str) -> dict[str, Any] | None:
        """按最新的每周时长和实际速度，重排在途计划里还没完成的任务日期。

        只动日期，不动任务内容、不调模型、不碰已完成的任务，所以是无损的，
        可以在「保存学习目标」和「完成一个任务」之后自动触发。
        任务内容本身要不要变（比如目标水平从「复述概念」改成「应对面试」）
        属于重新生成计划，那会丢掉当前进度，必须由用户显式确认，不在这里做。
        """
        daily_budget = self._daily_minutes_budget(user_id, book_id)
        if not daily_budget:
            return None
        payload = self.reader.read(allow_missing=True, allow_empty=False)
        if not isinstance(payload, dict) or not payload:
            return None

        factor = self.pace_factor(user_id, book_id)
        updated_plan: dict[str, Any] | None = None
        for key, record in payload.items():
            if not isinstance(record, dict):
                continue
            if record.get("userId") != user_id or record.get("bookId") != book_id:
                continue
            if record.get("status") == "completed":
                continue
            plan = record.get("plan")
            if not isinstance(plan, dict):
                continue
            updated_plan = self._apply_time_budget(
                plan,
                daily_budget=daily_budget,
                pace_factor=factor,
                only_unfinished=True,
            )
            self.persist_plan(
                book_id=book_id,
                diagnostic_id=str(record.get("diagnosticId", "")),
                plan=updated_plan,
                plan_key=key,
                user_id=user_id,
            )
        return updated_plan

    def create_from_material(
        self,
        *,
        book_id: str,
        title: str,
        goal: str,
        description: str,
        minutes: int,
        expected_completion_date: str,
        resources: list[dict[str, Any]],
        user_id: str = "",
    ) -> dict[str, Any]:
        """根据资料问答来源创建并持久化一个自定义学习任务。"""

        task_id = f"material-{book_id}-{uuid4().hex[:10]}"
        knowledge_point_ids = self._knowledge_points_for_resources(resources)
        task = LearningTask(
            id=task_id,
            title=title,
            type="qa_review",
            source="material_qa",
            minutes=minutes,
            status="todo",
            reason="基于资料问答来源创建",
            description=description or f"围绕“{goal}”复习资料并完成知识点整理。",
            learning_goal=goal,
            expected_completion_date=expected_completion_date,
            knowledge_point_ids=knowledge_point_ids,
        ).to_dict()

        return self.create_task_plan(
            book_id=book_id,
            task=task,
            goal=goal,
            goal_level="自定义学习目标",
            advice=["建议先阅读关联教材，再回到资料问答中进行复习和追问。"],
            resources=resources,
            plan_key=f"{book_id}:material:{task_id}",
            user_id=user_id,
        )

    @staticmethod
    def _knowledge_points_for_resources(resources: list[dict[str, Any]]) -> list[str]:
        """Use knowledge-point metadata supplied by the active material index."""
        points = {
            str(point_id)
            for item in resources
            for point_id in (item.get("knowledgePointIds") or item.get("knowledge_point_ids") or [])
            if point_id
        }
        return sorted(points) or ["unknown"]

    @staticmethod
    def _merge_resources(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for resource in [*existing, *incoming]:
            key = str(resource.get("title") or resource.get("id") or len(merged))
            merged[key] = resource
        return list(merged.values())

    @staticmethod
    def _book(book_id: str) -> dict[str, str]:
        """把教材编号转换为前端需要的教材展示信息。"""
        books = {
            "ml": {"id": "ml", "title": "《机器学习》", "shortTitle": "机器学习"},
            "dl": {"id": "dl", "title": "《深度学习》", "shortTitle": "深度学习"},
        }
        return books.get(book_id, {"id": book_id, "title": book_id, "shortTitle": book_id})

    @staticmethod
    def _goal_level(results: list[dict[str, Any]]) -> str:
        """根据所有知识点的诊断状态推断用户当前目标层级。"""
        statuses = [str(item.get("calibrated_status") or item.get("ai_status") or "") for item in results]
        if not statuses:
            return ""
        if all(status == STATUSES[-1] for status in statuses):
            return "能够迁移到项目实践"
        if any(status == STATUSES[1] for status in statuses):
            return "了解核心概念"
        return "能够独立完成基础练习"

    @staticmethod
    def _effective_status(result: dict[str, Any]) -> str:
        """优先使用校准状态，其次使用模型状态，最后回退到最低状态。"""
        return result.get("calibrated_status") or result.get("ai_status") or result.get("status") or STATUSES[0]

    def _status_rank(self, result: dict[str, Any]) -> int:
        """返回诊断状态在预设状态序列中的位置，用于任务排序。"""
        status = self._effective_status(result)
        return STATUSES.index(status) if status in STATUSES else 0
    

    def _build_planning_units(
        self,
        questions: list[dict[str, Any]],
        answer_records: list[dict[str, Any]],
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """把知识点诊断证据聚合成能力级计划单元。"""
        result_by_point = {str(item.get("knowledge_point_id")): item for item in results}
        records_by_question = {str(item.get("question_id")): item for item in answer_records}
        #记录能力
        units: dict[str, dict[str, Any]] = {}
        for question in questions:
            question_id = str(question.get("id", ""))
            #获取题目所属的能力
            ability_ids = [str(item) for item in question.get("ability_ids", []) if item]
            if not ability_ids:
                ability_ids = [f"knowledge:{question.get('tag', 'unknown')}" ]
            #获取题目所属的作答记录
            record = records_by_question.get(question_id, {})
            #获取题目所属的知识点
            knowledge_ids = [str(item) for item in question.get("knowledge_point_ids", []) if item]
            if not knowledge_ids and question.get("tag"):
                knowledge_ids = [str(question["tag"])]
            #按能力聚合
            for ability_id in ability_ids:
                unit = units.setdefault(
                    ability_id,
                    {
                        "ability_id": ability_id,
                        "knowledge_point_ids": [],
                        "chapter_ids": [],
                        "question_ids": [],
                        "correct": 0,
                        "answered": 0,
                        "skipped": 0,
                        "incorrect": 0,
                        "total": 0,
                        "statuses": [], #关联知识点的掌握状态
                    },
                )
                unit["question_ids"].append(question_id)
                unit["correct"] += int(bool(record.get("is_correct")))
                skipped = bool(record.get("skipped") or not record.get("submitted_answer"))
                unit["skipped"] += int(skipped)
                unit["answered"] += int(not skipped)
                unit["incorrect"] += int(not skipped and not record.get("is_correct"))
                unit["total"] += 1
                unit["knowledge_point_ids"] = sorted(set(unit["knowledge_point_ids"]) | set(knowledge_ids))
                chapter_id = str(question.get("chapter_id", ""))
                if chapter_id:
                    unit["chapter_ids"] = sorted(set(unit["chapter_ids"]) | {chapter_id})
                unit["statuses"].extend(
                    self._effective_status(result_by_point[item])
                    for item in knowledge_ids
                    if item in result_by_point
                )
        #目前是采用短板规则，即直接返回最弱
        for unit in units.values():
            unit["status"] = min(unit["statuses"], key=lambda value: STATUSES.index(value)) if unit["statuses"] else STATUSES[0]
            unit.pop("statuses", None)
        return list(units.values())
    
    #生成任务字段
    def _build_task(self, diagnostic_id: str, result: dict[str, Any], index: int, goal: str, session_budget: Any = None) -> dict[str, Any]:
        """把一个能力级计划单元转换为任务，知识点是任务的支撑范围。"""
        ability_id = str(result.get("ability_id", "ability"))
        #把内部能力 ID 转换为用户可读名称
        name = {"math": "数学能力", "algorithm": "算法能力", "programming": "编程能力", "conceptual": "概念理解能力"}.get(ability_id, ability_id.replace("_", " "))
        status = str(result.get("status", STATUSES[0]))
        correct = int(result.get("correct", 0))
        total = int(result.get("total", 0))
        minutes = self._minutes_for(status, session_budget)
        return LearningTask(
            id=f"{diagnostic_id}-ability-{ability_id}",
            ability_id=ability_id,
            knowledge_point_ids=result.get("knowledge_point_ids", []),
            chapter_ids=result.get("chapter_ids", []),
            question_ids=result.get("question_ids", []),
            title=f"提升{name}",
            type="concept_review" if index == 0 else "practice",
            source="diagnostic",
            minutes=minutes,
            status="in_progress" if index == 0 else "todo",
            reason=f"诊断结果为“{status}”，答对 {correct}/{total} 题",
            description=f"围绕“{goal}”提升{name}，复习关联知识点并完成迁移练习。",
        ).to_dict()

    @staticmethod
    def _minutes_for(status: str, session_budget: Any = None) -> int:
        """根据知识点掌握状态和用户的单次学习时长偏好估算任务时长。

        原来这里写死 25/20/15 分钟，跟用户在画像里选的单次时长完全无关——
        所以不管选 30 分钟还是 2 小时，排出来的任务都是二十几分钟。

        现在以单次时长偏好为基准按掌握程度缩放：越薄弱的知识点占满整段学习时间，
        越熟练的越短。偏好 30 分钟 → 30/23/15，和过去接近；
        偏好 120 分钟 → 120/90/60，就能排出一到两小时的任务。
        """
        base = int(session_budget) if session_budget else LearningPlanModule.DEFAULT_TASK_MINUTES
        base = max(5, min(LearningPlanModule.MAX_TASK_MINUTES, base))
        if status in {STATUSES[0], STATUSES[1]}:
            ratio = 1.0      # 不会 / 了解：占满一整段
        elif status == STATUSES[2]:
            ratio = 0.75     # 熟悉：巩固一下
        else:
            ratio = 0.5      # 掌握：快速回顾
        return max(5, int(round(base * ratio / 5) * 5))

    @staticmethod
    def _diagnostic_summary(question_evidence: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(question_evidence)
        answered = sum(item["outcome"] != "skipped" for item in question_evidence)
        correct = sum(item["outcome"] == "correct" for item in question_evidence)
        skipped = total - answered
        return {
            "totalQuestions": total,
            "answeredQuestions": answered,
            "skippedQuestions": skipped,
            "correctQuestions": correct,
            "incorrectQuestions": answered - correct,
            "accuracy": round(correct / answered * 100, 2) if answered else 0.0,
            "evidenceCoverage": "high" if total and skipped == 0 else "medium" if answered else "low",
        }

    @staticmethod
    def _build_question_evidence(
        questions: list[dict[str, Any]],
        answer_records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        records = {str(item.get("question_id", "")): item for item in answer_records}
        evidence: list[dict[str, Any]] = []
        for question in questions:
            question_id = str(question.get("id", ""))
            record = records.get(question_id, {})
            submitted_id = str(record.get("submitted_answer", ""))
            correct_id = str(record.get("correct_answer", ""))
            options = {
                str(option.get("id", "")): str(option.get("text", ""))
                for option in question.get("options", [])
                if isinstance(option, dict)
            }
            skipped = bool(record.get("skipped") or not submitted_id)
            outcome = "skipped" if skipped else "correct" if record.get("is_correct") else "incorrect"
            evidence.append(
                {
                    "questionId": question_id,
                    "title": str(question.get("title", "")),
                    "submittedAnswerId": submitted_id,
                    "submittedAnswerText": options.get(submitted_id, ""),
                    "correctAnswerId": correct_id,
                    "correctAnswerText": options.get(correct_id, ""),
                    "outcome": outcome,
                    "knowledgePointIds": list(
                        question.get("knowledge_point_ids") or ([question.get("tag")] if question.get("tag") else [])
                    ),
                    "abilityIds": list(question.get("ability_ids", [])),
                    "chapterId": str(question.get("chapter_id", "")),
                    "sectionIds": list(question.get("section_ids", [])),
                    "hintCount": int(record.get("hint_count", 0)),
                    "retryCount": int(record.get("retry_count", 0)),
                    "isIndependent": bool(record.get("is_independent", True)),
                    "taskMode": str(question.get("task_mode", "diagnostic")),
                }
            )
        return evidence

    @staticmethod
    def _knowledge_point_contexts(
        results: list[dict[str, Any]],
        answer_records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        contexts: list[dict[str, Any]] = []
        for result in results:
            point_id = str(result.get("knowledge_point_id", ""))
            point_records = [
                item
                for item in answer_records
                if point_id in (item.get("knowledge_point_ids") or [item.get("knowledge_point_id", "")])
            ]
            answered = [item for item in point_records if item.get("submitted_answer") and not item.get("skipped")]
            algorithm_level = str(result.get("mastery_level") or result.get("ai_status") or STATUSES[0])
            calibrated_level = result.get("user_calibrated_level") or result.get("calibrated_status")
            contexts.append(
                {
                    "knowledgePointId": point_id,
                    "knowledgePointName": KNOWLEDGE_POINT_NAMES.get(point_id, point_id),
                    "algorithmMasteryLevel": algorithm_level,
                    "userCalibratedLevel": calibrated_level,
                    "effectiveMasteryLevel": str(calibrated_level or algorithm_level),
                    "masteryScore": float(result.get("mastery_score", 0.0)),
                    "confidence": float(result.get("confidence", 0.0)),
                    "roundCorrect": sum(bool(item.get("is_correct")) for item in answered),
                    "roundIncorrect": sum(not item.get("is_correct") for item in answered),
                    "roundAnswered": len(answered),
                    "roundSkipped": len(point_records) - len(answered),
                    "roundTotal": len(point_records),
                    "memoryStatus": str(result.get("memory_status", "未验证")),
                    "memoryStabilityDays": float(result.get("memory_stability_days", 0.0)),
                    "nextReviewAt": result.get("next_review_at"),
                    "evidenceSummary": result.get("evidence_summary", {}),
                    "reasonCodes": list(result.get("reason_codes", [])),
                }
            )
        return contexts

    @staticmethod
    def _resource_candidates(
        book_id: str,
        questions: list[dict[str, Any]],
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        tested_ids = {
            str(item.get("knowledge_point_id", ""))
            for item in results
            if item.get("knowledge_point_id")
        }
        grouped: dict[str, dict[str, Any]] = {}
        for question in questions:
            source = str(question.get("source", "")).strip()
            point_ids = [
                str(item)
                for item in (question.get("knowledge_point_ids") or [question.get("tag")])
                if item
            ]
            if not source or (tested_ids and not tested_ids.intersection(point_ids)):
                continue
            parts = [part.strip() for part in source.replace("\\", "/").split("/") if part.strip()]
            grouped.setdefault(
                source,
                {
                    "id": f"diagnostic-source-{len(grouped) + 1}",
                    "type": "教材",
                    "title": parts[-1] if parts else source,
                    "location": source,
                    "excerpt": f"诊断题关联资料，覆盖知识点：{'、'.join(point_ids)}。",
                    "bookId": book_id,
                    "chapterId": str(question.get("chapter_id", "")),
                    "sectionId": str(next(iter(question.get("section_ids", [])), "")),
                    "contentUnitId": "",
                    "knowledgePointIds": point_ids,
                },
            )
        return list(grouped.values())

    def _learner_preferences(self, user_id: str, book_id: str) -> dict[str, Any]:
        if self.learner_profile is None:
            return {}
        learning_domain = {
            "ml": "machine_learning",
            "ml-001": "machine_learning",
            "dl": "deep_learning",
            "dl-001": "deep_learning",
        }.get(book_id, book_id)
        profile = self.learner_profile.get(user_id, learning_domain)
        if profile is None:
            return {}
        preferences = profile.preferences
        return {
            "sessionTimeBudgetMinutes": int(preferences.session_duration_minutes),
            "activityTypes": list(preferences.activity_types),
            "contentStyle": preferences.content_style,
            "difficulty": preferences.difficulty,
            "learningFrequency": preferences.learning_frequency,
        }
