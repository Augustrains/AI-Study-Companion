"""诊断模块的 LLM 调用入口。"""

from __future__ import annotations

from sdk.llm_client import LLMClient, NullLLMClient

from .models import KnowledgePointQuestionPlan, QuestionPlanningInput
from .services import build_question_planning_prompt, parse_question_plan


class DiagnosticAgent:
    """调用一次 LLM，返回经过后端约束的知识点出题计划。"""

    MAX_TOTAL_QUESTIONS = 8

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or NullLLMClient()

    def plan_questions(self, agent_input: QuestionPlanningInput) -> list[KnowledgePointQuestionPlan]:
        prompt = build_question_planning_prompt(agent_input)
        response = self.llm_client.generate(prompt)
        return parse_question_plan(response, agent_input, self.MAX_TOTAL_QUESTIONS)
