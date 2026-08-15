"""资料问答 Agent。"""

from __future__ import annotations

import json

from sdk.llm_client import LLMClient, NullLLMClient

from .models import MaterialQaAgentInput, MaterialQaAgentOutput


class MaterialQaAgent:
    """使用对话历史和 RAG 检索上下文生成资料问答回答。"""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or NullLLMClient()

    def generate(self, agent_input: MaterialQaAgentInput) -> MaterialQaAgentOutput:
        """调用 LLM 生成回答，引用和知识点由检索结果提供。"""

        raw_response = self.llm_client.generate(self._build_prompt(agent_input))
        answer, refused = self._parse_response(raw_response)
        citations = [] if refused else agent_input.retrieval.citations
        related_knowledge_points = sorted(
            {
                point
                for citation in citations
                for point in citation.knowledge_point_ids
            }
        )
        return MaterialQaAgentOutput(
            answer=answer,
            refused=refused,
            citations=citations,
            related_knowledge_points=related_knowledge_points,
            recommended_action=(
                "请换一个与当前教材相关的问题，或补充能够支持该问题的学习资料。"
                if refused
                else "如需继续学习，可以结合上述引用资料追问具体概念或示例。"
            ),
        )

    @staticmethod
    def _parse_response(raw_response: str) -> tuple[str, bool]:
        """Parse the model's structured answer and hide citations on invalid output."""

        content = raw_response.strip()
        if content.startswith("```") and content.endswith("```"):
            lines = content.splitlines()
            content = "\n".join(lines[1:-1]).strip()
        try:
            payload = json.loads(content)
            answer = payload["answer"]
            refused = payload["refused"]
            if not isinstance(answer, str) or not answer.strip() or not isinstance(refused, bool):
                raise ValueError("invalid material QA response fields")
            return answer.strip(), refused
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return content or "当前资料不足以回答这个问题。", True

    @staticmethod
    def _build_prompt(agent_input: MaterialQaAgentInput) -> str:
        history = "\n".join(
            f"{'用户' if message.role == 'user' else '助手'}：{message.content}"
            for message in agent_input.history
        ) or "（无历史对话）"

        materials = []
        for index, chunk in enumerate(agent_input.retrieval.chunks, start=1):
            source = chunk.source
            materials.append(
                f"[资料{index}] {source.title}（{source.location}）\n{chunk.text}"
            )
        context = "\n\n".join(materials) or "（未检索到相关资料）"

        return f"""你是 Study Companion 的资料问答助手。请严格遵守以下规则：
1. 优先依据给出的检索资料回答，不要编造资料中没有的事实。
2. 使用清晰、准确、适合学习者理解的中文；必要时分点说明。
3. 如果资料不足以回答，应明确说明资料不足，并指出还需要什么信息。
4. 当问题与资料无关，或资料不足以可靠回答时，将 refused 设为 true，并在 answer 中简要说明拒答原因。
5. 只有回答能够由检索资料直接支持时，才将 refused 设为 false。
6. 只输出一个合法 JSON 对象，不要使用 Markdown 代码块，不要输出思考过程或其他文字。格式必须是：
{{"refused": false, "answer": "基于资料的最终回答"}}

历史对话：
{history}

检索资料：
{context}

当前问题：
{agent_input.current_question}
"""
