"""诊断模块的 LLM 调用入口。"""

from __future__ import annotations

from modules.context.renderer import ContextRenderer
from sdk.llm_client import LLMClient, NullLLMClient, generate_messages_compat

from .models import KnowledgePointQuestionPlan, QuestionPlanningInput
from .services import build_question_planning_prompt, parse_question_plan


class DiagnosticAgent:
    """调用一次 LLM，返回经过后端约束的知识点出题计划。"""

    MAX_TOTAL_QUESTIONS = 8

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or NullLLMClient()

    def plan_questions(
        self, agent_input: QuestionPlanningInput
    ) -> list[KnowledgePointQuestionPlan]:
        if agent_input.context is None:
            response = self.llm_client.generate(
                build_question_planning_prompt(agent_input)
            )
        else:
            messages = ContextRenderer().render(
                agent_input.context,
                agent_instructions="""
你是 Study Companion 的自适应选题 Agent。只能根据后端给出的安全诊断上下文选题。
questionCount 必须是 0 到 min(4, availableQuestionCount) 的整数，总数不得超过 8。
taskMode 只能是 diagnostic、guided_practice、independent、retrieval、remediation、challenge。
优先选择与学习目标相关、薄弱或到期复习的知识点。
只输出 JSON：{"selections":[{"knowledgePointId":"知识点ID","questionCount":2,"taskMode":"diagnostic"}]}
""",
            )
            response = generate_messages_compat(self.llm_client, messages)
        return parse_question_plan(response, agent_input, self.MAX_TOTAL_QUESTIONS)
