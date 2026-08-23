"""诊断模块的 LLM 调用入口。"""

from __future__ import annotations

import logging

from modules.common.errors import AppError
from sdk.llm_client import LLMClient, NullLLMClient

from .models import KnowledgePointQuestionPlan, QuestionPlanningInput
from .services import build_question_planning_prompt, parse_question_plan

logger = logging.getLogger(__name__)


class DiagnosticAgent:
    """调用一次 LLM，返回经过后端约束的知识点出题计划。"""

    MAX_TOTAL_QUESTIONS = 8

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or NullLLMClient()

    def plan_questions(self, agent_input: QuestionPlanningInput) -> list[KnowledgePointQuestionPlan]:
        """生成出题计划。模型不可用时退回规则计划，而不是让整个诊断起不来。

        背景：`parse_question_plan` 本来就带一套规则兜底（`_fallback_question_plan`），
        但它只在「模型返回了内容、内容解析不了」时生效。模型调用本身抛异常
        （key 失效、超时、网络不通 → ExternalServiceError）时异常直接冒到
        LangGraph 的 load_questions 节点，诊断在第一步就 502。

        出题计划只是「每个知识点出几道、什么模式」的编排，规则版完全够用；
        而且整条诊断链路里只有这一处调模型（答案评估、掌握度判定都是规则驱动的），
        所以兜住这里，模型不可用时整个诊断闭环仍然跑得通，只是选题不那么个性化。
        """

        try:
            response = self.llm_client.generate(build_question_planning_prompt(agent_input))
        except AppError as error:
            # 只吞「外部服务不可用」这类可降级的异常，配置错误等同样是 AppError，
            # 但对出题来说结果一样：拿不到模型输出，用规则计划继续。
            logger.warning(
                "question planning fell back to rule-based plan: code=%s details=%s",
                error.code,
                error.details,
            )
            response = ""
        except Exception:  # noqa: BLE001 - 出题不该因为任何意外把诊断整个打死
            logger.exception("question planning failed unexpectedly, falling back to rule-based plan")
            response = ""
        # response 为空字符串时，parse_question_plan 解析失败并整体回落到规则计划。
        return parse_question_plan(response, agent_input, self.MAX_TOTAL_QUESTIONS)
