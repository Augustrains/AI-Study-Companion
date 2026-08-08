from domain.models import KnowledgePointResult
from sdk.llm_client import LLMClient


class DiagnosticAgent:
    """解释诊断结果，不直接修改学习状态。"""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client

    def explain(self, result: KnowledgePointResult) -> str:
        # 后续可将结构化结果交给 LLM；Demo 先保证无外部服务也能运行。
        if result.ai_status == "不会":
            return f"该知识点答对 {result.correct}/{result.total} 题，建议先补充基础概念。"
        if result.ai_status == "基本了解":
            return f"该知识点答对 {result.correct}/{result.total} 题，已具备基础理解，建议完成典型练习。"
        if result.ai_status == "熟悉":
            return f"该知识点答对 {result.correct}/{result.total} 题，能够完成部分典型题目，可通过复测确认稳定性。"
        return f"该知识点答对 {result.correct}/{result.total} 题，当前表现较好，建议通过应用题进一步确认。"
