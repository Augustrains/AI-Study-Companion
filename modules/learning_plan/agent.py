"""LLM-backed learning-plan generation with deterministic safeguards."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from modules.common.errors import ConfigurationError, ExternalServiceError
from sdk.llm_client import LLMClient, NullLLMClient

from .models import LEARNING_TASK_TYPES_BY_SOURCE


@dataclass(frozen=True)
class LearningPlanAgentInput:
    """Verified facts and bounded choices available to the planning agent."""

    book: dict[str, str]
    goal: str
    goal_level: str
    diagnostic_summary: dict[str, Any]
    knowledge_point_results: list[dict[str, Any]] = field(default_factory=list)
    ability_units: list[dict[str, Any]] = field(default_factory=list)
    question_evidence: list[dict[str, Any]] = field(default_factory=list)
    candidate_resources: list[dict[str, Any]] = field(default_factory=list)
    calibration: dict[str, Any] = field(default_factory=dict)
    learner_preferences: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)


class LearningPlanAgent:
    """Generate a plan from verified diagnosis facts.

    The model may choose ordering and learner-facing task wording, but backend
    templates remain authoritative for IDs, evidence links, status and dates.
    """

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or NullLLMClient()
    
    #整个类的主入口
    def build(
        self,
        agent_input: LearningPlanAgentInput,
        *,
        fallback_tasks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate and validate an LLM plan, falling back on local templates."""
        
        #生成本地兜底计划
        fallback = self._fallback_plan(agent_input, fallback_tasks)
        try:
            raw_response = self.llm_client.generate(self._build_prompt(agent_input))
        except (ConfigurationError, ExternalServiceError):
            return fallback
        if not raw_response.strip():
            return fallback

        try:
            payload = self._parse_json_response(raw_response)
            tasks = self._validated_tasks(payload, agent_input, fallback_tasks)
            advice = self._validated_advice(payload)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return fallback

        return {
            "book": agent_input.book,
            "goal": agent_input.goal,
            "goalLevel": agent_input.goal_level,
            "tasks": tasks,
            "advice": advice or fallback["advice"],
            "resources": agent_input.candidate_resources,
        }

    @staticmethod
    def _parse_json_response(response: str) -> dict[str, Any]:
        text = response.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1]).strip()
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise TypeError("learning plan response must be an object")
        return payload

    def _validated_tasks(
        self,
        payload: dict[str, Any],
        agent_input: LearningPlanAgentInput,
        fallback_tasks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        raw_tasks = payload.get("tasks")
        if not isinstance(raw_tasks, list):
            raise TypeError("learning plan tasks must be a list")

        allowed_types = set(
            agent_input.constraints.get("allowedTaskTypes")
            or LEARNING_TASK_TYPES_BY_SOURCE["diagnostic"]
        )
        minimum_minutes = int(agent_input.constraints.get("minTaskMinutes", 5))
        maximum_minutes = int(agent_input.constraints.get("maxTaskMinutes", 60))
        fallback_by_ability = {
            str(task.get("ability_id", "")): task
            for task in fallback_tasks
            if task.get("ability_id")
        }
        generated_by_ability: dict[str, dict[str, Any]] = {}
        generated_order: list[str] = []

        for raw_task in raw_tasks:
            if not isinstance(raw_task, dict):
                continue
            ability_id = str(raw_task.get("abilityId", ""))
            template = fallback_by_ability.get(ability_id)
            if template is None or ability_id in generated_by_ability:
                continue
            task_type = str(raw_task.get("type", ""))
            if task_type not in allowed_types:
                task_type = str(template["type"])
            try:
                minutes = int(raw_task.get("minutes", template["minutes"]))
            except (TypeError, ValueError):
                minutes = int(template["minutes"])

            generated = dict(template)
            generated.update(
                {
                    "title": self._bounded_text(raw_task.get("title"), template["title"], 100),
                    "type": task_type,
                    "minutes": max(minimum_minutes, min(minutes, maximum_minutes)),
                    "reason": self._bounded_text(raw_task.get("reason"), template["reason"], 300),
                    "description": self._bounded_text(
                        raw_task.get("description"), template["description"], 500
                    ),
                }
            )
            generated_by_ability[ability_id] = self._add_schedule(generated)
            generated_order.append(ability_id)

        # A malformed or incomplete model response must not silently remove a
        # diagnosed ability from the plan. Missing units retain local defaults.
        for ability_id, template in fallback_by_ability.items():
            if ability_id not in generated_by_ability:
                generated_by_ability[ability_id] = self._constrained_fallback_task(template, agent_input)
                generated_order.append(ability_id)

        if not generated_order and fallback_tasks:
            raise ValueError("model returned no recognized planning units")
        return [generated_by_ability[ability_id] for ability_id in generated_order]

    @staticmethod
    def _validated_advice(payload: dict[str, Any]) -> list[str]:
        raw_advice = payload.get("advice", [])
        if not isinstance(raw_advice, list):
            return []
        return [str(item).strip()[:300] for item in raw_advice if str(item).strip()][:5]

    @staticmethod
    def _bounded_text(value: Any, fallback: str, limit: int) -> str:
        text = str(value).strip() if value is not None else ""
        return (text or fallback)[:limit]

    @staticmethod
    def _add_schedule(task: dict[str, Any]) -> dict[str, Any]:
        scheduled = dict(task)
        scheduled.setdefault("expected_completion_date", date.today().isoformat())
        return scheduled

    def _constrained_fallback_task(
        self,
        task: dict[str, Any],
        agent_input: LearningPlanAgentInput,
    ) -> dict[str, Any]:
        constrained = dict(task)
        minimum = int(agent_input.constraints.get("minTaskMinutes", 5))
        maximum = int(agent_input.constraints.get("maxTaskMinutes", 60))
        constrained["minutes"] = max(minimum, min(int(constrained.get("minutes", minimum)), maximum))
        return self._add_schedule(constrained)

    def _fallback_plan(
        self,
        agent_input: LearningPlanAgentInput,
        fallback_tasks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        results = list(agent_input.knowledge_point_results)
        records = list(agent_input.question_evidence)
        weak_results = sorted(results, key=self._result_score)
        accuracy = int(round(float(agent_input.diagnostic_summary.get("accuracy", 0))))
        return {
            "book": agent_input.book,
            "goal": agent_input.goal,
            "goalLevel": agent_input.goal_level,
            "tasks": [self._constrained_fallback_task(task, agent_input) for task in fallback_tasks],
            "advice": self._build_advice(weak_results, records, accuracy),
            "resources": agent_input.candidate_resources,
        }

    @staticmethod
    def _result_score(result: dict[str, Any]) -> tuple[int, float]:
        status = result.get("effectiveMasteryLevel") or result.get("masteryLevel") or ""
        correct = int(result.get("roundCorrect", 0))
        total = int(result.get("roundTotal", 0))
        return (0 if status in {"未测评", "不会", "了解"} else 1, correct / total if total else 0)

    @staticmethod
    def _build_advice(
        weak_results: list[dict[str, Any]],
        records: list[dict[str, Any]],
        accuracy: int,
    ) -> list[str]:
        advice: list[str] = []
        if weak_results:
            weakest = weak_results[0]
            name = str(weakest.get("knowledgePointName") or weakest.get("knowledgePointId") or "当前薄弱知识点")
            advice.append(f"诊断正确率为 {accuracy}%；优先学习“{name}”，再进行针对性复测。")
        skipped = sum(1 for item in records if item.get("outcome") == "skipped")
        if skipped:
            advice.append(f"本次诊断有 {skipped} 道题未完成，相关结论的证据仍需补充。")
        if records and not advice:
            advice.append(f"本次诊断正确率为 {accuracy}%，建议继续完成计划中的下一项任务。")
        return advice

    @staticmethod
    def _build_prompt(agent_input: LearningPlanAgentInput) -> str:
        context = {
            "book": agent_input.book,
            "learningGoal": agent_input.goal,
            "goalLevel": agent_input.goal_level,
            "diagnosticSummary": agent_input.diagnostic_summary,
            "knowledgePointResults": agent_input.knowledge_point_results,
            "abilityUnits": agent_input.ability_units,
            "questionEvidence": agent_input.question_evidence,
            "candidateResources": agent_input.candidate_resources,
            "calibration": agent_input.calibration,
            "learnerPreferences": agent_input.learner_preferences,
            "constraints": agent_input.constraints,
        }
        return f"""你是 Study Companion 的学习计划 Agent。请根据后端已经验证的诊断事实生成学习任务排序和学习建议。

规则：
1. 不得修改或重新计算掌握等级、掌握分数、正确率和置信度。
2. 每个任务的 abilityId 只能取自 abilityUnits；不得创造能力、知识点、题目或资料 ID。
3. 每个 abilityId 最多输出一个任务，并覆盖所有 abilityUnits。
4. type 只能取 constraints.allowedTaskTypes；minutes 必须在约束范围内。
5. 如果提供 learnerPreferences.sessionTimeBudgetMinutes，每项任务时长不得超过该值；它是用户期望的单次学习时长，不是整个计划的总时长。
6. 优先处理有效掌握等级较低、答错较多或用户校准后较弱的能力，并参考用户填写的 calibration.reason。
7. title、reason、description 必须是简洁、可执行的中文，不要声称用户做过输入中没有记录的行为。
8. candidateResources 仅包含本轮诊断知识点的关联来源；不得要求或创造完整资源目录。
9. 只输出合法 JSON，不要输出 Markdown 或思考过程。

输出格式：
{{
  "tasks": [
    {{
      "abilityId": "输入中的能力ID",
      "title": "任务标题",
      "type": "concept_review|practice|retest",
      "minutes": 20,
      "reason": "基于诊断证据的原因",
      "description": "具体执行说明"
    }}
  ],
  "advice": ["总体学习建议"]
}}

输入：
{json.dumps(context, ensure_ascii=False)}
"""
