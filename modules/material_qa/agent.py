from __future__ import annotations

from .models import MaterialQaAgentInput, MaterialQaAgentOutput


class MaterialQaAgent:
    """资料问答 Agent 的临时实现，后续替换为真实模型调用。"""

    def generate(self, agent_input: MaterialQaAgentInput) -> MaterialQaAgentOutput:
        """根据历史对话、当前问题和 RAG 上下文生成回答。"""

        history_count = len(agent_input.history)
        answer = (
            f"测试对话字段：已接收历史对话 {history_count} 条；"
            f"当前问题：{agent_input.current_question}；"
            f"检索文本：{agent_input.retrieval.text or '暂无检索结果'}"
        )
        return MaterialQaAgentOutput(
            answer=answer,
            citations=agent_input.retrieval.citations,
            related_knowledge_points=sorted({
                point
                for citation in agent_input.retrieval.citations
                for point in citation.knowledge_point_ids
            }),
            recommended_action="测试下一步操作",
        )
