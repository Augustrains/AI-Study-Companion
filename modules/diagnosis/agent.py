"""AI-facing interfaces for diagnostic interpretation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sdk.llm_client import LLMClient, NullLLMClient


TASK_MODES = (
    "diagnostic",
    "guided_practice",
    "independent",
    "retrieval",
    "remediation",
    "challenge",
)


@dataclass(frozen=True)
class QuestionPlanningInput:
    """Facts available to the Agent before a diagnostic round is assembled."""

    learning_goal: str
    knowledge_point_mastery: dict[str, str]
    knowledge_point_memory: dict[str, dict[str, Any]]
    available_question_counts: dict[str, int]
    knowledge_point_catalog: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgePointQuestionPlan:
    """The Agent's bounded selection decision for one knowledge point."""

    knowledge_point_id: str
    question_count: int
    task_mode: str

@dataclass(frozen=True)
class DiagnosticAnalysisInput:
    """实际交给agent"""

    diagnosis_id: str
    learning_goal: str
    total_questions: int
    answered_questions: int
    skipped_questions: int
    correct_questions: int
    accuracy: float
    level: str
    confidence: str
    knowledge_point_results: list[dict[str, Any]] = field(default_factory=list)
    question_results: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class DiagnosticAnalysisOutput:
    """Text produced by the diagnostic AI interface."""

    evidence: str
    answer_performance: str


class DiagnosticAgent:
    """Generate learner-facing interpretations from verified diagnostic data."""

    MAX_TOTAL_QUESTIONS = 8
    DEFAULT_EVIDENCE = "目前证据来自默认字段"
    DEFAULT_ANSWER_PERFORMANCE = "目前作答表现来自默认字段"

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or NullLLMClient()

    def plan_questions(self, planning_input: QuestionPlanningInput) -> list[KnowledgePointQuestionPlan]:
        """Ask the LLM how many questions and which teaching type each point needs."""

        prompt = self._build_question_planning_prompt(planning_input)
        response = self.llm_client.generate(prompt)
        if not response.strip():
            return self._limit_total_questions(self._fallback_question_plan(planning_input))

        try:
            payload = self._parse_json_response(response)
            raw_selections = payload.get("selections", []) if isinstance(payload, dict) else []
            by_id = {
                str(item.get("knowledgePointId", "")): item
                for item in raw_selections
                if isinstance(item, dict)
            }
        except (TypeError, ValueError, json.JSONDecodeError):
            return self._limit_total_questions(self._fallback_question_plan(planning_input))

        fallback = {
            item.knowledge_point_id: item
            for item in self._fallback_question_plan(planning_input)
        }
        result: list[KnowledgePointQuestionPlan] = []
        eligible_counts = self._eligible_question_counts(planning_input)
        for point_id, available in eligible_counts.items():
            item = by_id.get(point_id, {})
            task_mode = str(item.get("taskMode", ""))
            if task_mode not in TASK_MODES:
                task_mode = fallback[point_id].task_mode
            if task_mode == "retrieval" and not self._is_review_due(
                planning_input.knowledge_point_memory.get(point_id, {})
            ):
                task_mode = fallback[point_id].task_mode
            try:
                requested_count = int(item.get("questionCount"))
            except (TypeError, ValueError):
                requested_count = fallback[point_id].question_count
            result.append(
                KnowledgePointQuestionPlan(
                    knowledge_point_id=point_id,
                    question_count=max(0, min(requested_count, available, 4)),
                    task_mode=task_mode,
                )
            )
        preferred_ids = [
            str(item.get("knowledgePointId", ""))
            for item in raw_selections
            if isinstance(item, dict)
        ]
        return self._limit_total_questions(result, preferred_ids=preferred_ids)

    @classmethod
    def _limit_total_questions(
        cls,
        plan: list[KnowledgePointQuestionPlan],
        *,
        preferred_ids: list[str] | None = None,
    ) -> list[KnowledgePointQuestionPlan]:
        """Apply a backend-owned cap while preserving the public plan order."""

        preference = {point_id: index for index, point_id in enumerate(preferred_ids or [])}
        mode_priority = {
            "remediation": 0,
            "diagnostic": 1,
            "guided_practice": 2,
            "retrieval": 3,
            "independent": 4,
            "challenge": 5,
        }
        ordered = sorted(
            enumerate(plan),
            key=lambda value: (
                preference.get(value[1].knowledge_point_id, len(preference)),
                mode_priority.get(value[1].task_mode, 99),
                value[0],
            ),
        )
        remaining = cls.MAX_TOTAL_QUESTIONS
        bounded_counts: dict[str, int] = {}
        for _, item in ordered:
            count = min(item.question_count, remaining)
            bounded_counts[item.knowledge_point_id] = count
            remaining -= count
        return [
            KnowledgePointQuestionPlan(
                knowledge_point_id=item.knowledge_point_id,
                question_count=bounded_counts.get(item.knowledge_point_id, 0),
                task_mode=item.task_mode,
            )
            for item in plan
        ]

    @staticmethod
    def _parse_json_response(response: str) -> Any:
        text = response.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1]).strip()
        return json.loads(text)

    @staticmethod
    def _build_question_planning_prompt(planning_input: QuestionPlanningInput) -> str:
        eligible_counts = DiagnosticAgent._eligible_question_counts(planning_input)
        points = [
            {
                "knowledgePointId": point_id,
                "name": planning_input.knowledge_point_catalog.get(point_id, {}).get("name", ""),
                "description": planning_input.knowledge_point_catalog.get(point_id, {}).get("description", ""),
                "mastery": planning_input.knowledge_point_mastery.get(point_id, "未测评"),
                "memory": planning_input.knowledge_point_memory.get(point_id, {}),
                "availableQuestionCount": count,
            }
            for point_id, count in eligible_counts.items()
        ]
        return f"""你是 Study Companion 的自适应选题 Agent。请根据掌握状态和记忆信息，决定本轮每个知识点需要几道题以及掌握度算法使用的 taskMode。

规则：
1. 只能使用输入中的 knowledgePointId，不得创造新 ID。
2. questionCount 必须是 0 到 min(4, availableQuestionCount) 的整数；0 表示本轮跳过。所有知识点的 questionCount 总和不得超过 8。
3. taskMode 只能是 diagnostic、guided_practice、independent、retrieval、remediation、challenge 之一。
4. 优先选择与学习目标直接相关、当前薄弱或到期复习的知识点；不要为了覆盖全部候选知识点而出题。
5. 未测评或证据不足使用 diagnostic；不会使用 remediation；了解且需要引导使用 guided_practice；熟悉使用 independent；只有 nextReviewAt 已到期才使用 retrieval；稳定掌握且无需复测时可使用 challenge。
6. 只输出 JSON，不要输出解释、Markdown 或思考过程。

学习目标：{planning_input.learning_goal or '未指定'}
候选知识点：{json.dumps(points, ensure_ascii=False)}

输出格式：
{{"selections":[{{"knowledgePointId":"知识点ID","questionCount":2,"taskMode":"independent"}}]}}
"""

    @staticmethod
    def _eligible_question_counts(planning_input: QuestionPlanningInput) -> dict[str, int]:
        available = planning_input.available_question_counts
        catalog = planning_input.knowledge_point_catalog
        if not catalog:
            return dict(available)

        goal = DiagnosticAgent._normalized_goal(planning_input.learning_goal)
        goal_bigrams = DiagnosticAgent._bigrams(goal)
        goal_matches: set[str] = set()
        if goal_bigrams:
            for point_id, metadata in catalog.items():
                name = DiagnosticAgent._normalized_text(metadata.get("name", ""))
                description = DiagnosticAgent._normalized_text(metadata.get("description", ""))
                name_overlap = len(goal_bigrams & DiagnosticAgent._bigrams(name))
                description_overlap = len(goal_bigrams & DiagnosticAgent._bigrams(description))
                if name_overlap >= 2 or description_overlap >= 4:
                    goal_matches.add(point_id)

        memory_points = {
            point_id
            for point_id, level in planning_input.knowledge_point_mastery.items()
            if level != "掌握" or DiagnosticAgent._is_review_due(
                planning_input.knowledge_point_memory.get(point_id, {})
            )
        }
        eligible = (goal_matches | memory_points) & set(available)
        if not eligible:
            return dict(available)
        return {point_id: count for point_id, count in available.items() if point_id in eligible}

    @staticmethod
    def _normalized_text(value: str) -> str:
        return "".join(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", value.lower()))

    @staticmethod
    def _normalized_goal(value: str) -> str:
        text = DiagnosticAgent._normalized_text(value)
        for phrase in ("理解", "掌握", "学习", "复习", "熟悉", "巩固", "基础", "知识点", "相关", "以及"):
            text = text.replace(phrase, "")
        return text

    @staticmethod
    def _bigrams(value: str) -> set[str]:
        return {value[index:index + 2] for index in range(max(0, len(value) - 1))}

    @staticmethod
    def _is_review_due(memory: dict[str, Any]) -> bool:
        value = memory.get("next_review_at") or memory.get("nextReviewAt")
        if not value:
            return False
        try:
            scheduled = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return False
        return scheduled <= datetime.now(scheduled.tzinfo)

    @classmethod
    def _fallback_question_plan(cls, planning_input: QuestionPlanningInput) -> list[KnowledgePointQuestionPlan]:
        """Keep local/test flows usable when the explicitly configured LLM returns no text."""

        count_by_mastery = {
            "未测试": 4,
            "未测评": 4,
            "不会": 4,
            "了解": 3,
            "熟悉": 2,
            "掌握": 1,
        }
        mode_by_mastery = {
            "未测试": "diagnostic",
            "未测评": "diagnostic",
            "不会": "remediation",
            "了解": "guided_practice",
            "熟悉": "independent",
            "掌握": "challenge",
        }
        result = []
        for point_id, available in cls._eligible_question_counts(planning_input).items():
            mastery = planning_input.knowledge_point_mastery.get(point_id, "未测评")
            mode = mode_by_mastery.get(mastery, "diagnostic")
            if mastery == "掌握" and cls._is_review_due(
                planning_input.knowledge_point_memory.get(point_id, {})
            ):
                mode = "retrieval"
            result.append(KnowledgePointQuestionPlan(
                knowledge_point_id=point_id,
                question_count=min(count_by_mastery.get(mastery, 3), available, 4),
                task_mode=mode,
            ))
        return result

    async def analyze_performance(
        self,
        analysis_input: DiagnosticAnalysisInput,
    ) -> DiagnosticAnalysisOutput:
        """Return a placeholder until the real LLM implementation is connected."""
        del analysis_input
        return DiagnosticAnalysisOutput(
            evidence=self.DEFAULT_EVIDENCE,
            answer_performance=self.DEFAULT_ANSWER_PERFORMANCE,
        )
