"""资料问答 Agent。"""

from __future__ import annotations

import json

from sdk.llm_client import LLMClient, NullLLMClient

from .models import MaterialQaAgentInput, MaterialQaAgentOutput


class MaterialQaAgent:
    """使用对话历史和 RAG 检索上下文生成资料问答回答。"""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or NullLLMClient()

    # 通用模型回答的固定前缀。放在 answer 里而不是只靠 answered_by_general_model 字段，
    # 是为了让复制走文本、脱离前端标注的场景也能看出这段内容未经教材核对。
    GENERAL_ANSWER_PREFIX = "（以下内容来自通用模型，未在当前教材中找到依据，请谨慎参考）\n\n"

    def generate(self, agent_input: MaterialQaAgentInput) -> MaterialQaAgentOutput:
        """调用 LLM 生成回答，引用和知识点由检索结果提供。"""

        raw_response = self.llm_client.generate(self._build_prompt(agent_input))
        answer, refused = self._parse_response(raw_response)

        # 教材内答不出、且用户显式允许降级时，再发一次「通用知识」提示词。
        # 只有拒答分支才会走到第二次调用，正常有出处的问答仍然是一次调用。
        if refused and agent_input.allow_general_fallback:
            return self._general_fallback(agent_input, refusal_reason=answer)

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

    def _general_fallback(
        self,
        agent_input: MaterialQaAgentInput,
        *,
        refusal_reason: str,
    ) -> MaterialQaAgentOutput:
        """检索不足时的降级回答：用通用知识作答，但不给任何教材引用。

        与正常路径的区别是刻意的：
          - citations 恒为空——这条回答没有教材出处，给引用就是造假；
          - related_knowledge_points 恒为空——掌握度只由诊断与练习产生，
            通用回答不应该影响任何知识点的掌握判断；
          - answered_by_general_model=True，前端据此打标注。
        """

        raw_response = self.llm_client.generate(self._build_general_prompt(agent_input))
        answer, failed = self._parse_response(raw_response)
        if failed and not answer.strip():
            answer = "通用模型也没有给出可用的回答，建议换一种问法。"
        return MaterialQaAgentOutput(
            answer=f"{self.GENERAL_ANSWER_PREFIX}{answer}",
            # 这里 refused=False：用户已经知道并接受了「没有教材依据」这件事，
            # 拿到的是一个真实回答，不该再被前端当作拒答处理。
            refused=False,
            citations=[],
            related_knowledge_points=[],
            recommended_action=(
                "这条回答未经教材验证，也不会计入学习记录。"
                f"教材内未找到依据的原因：{refusal_reason.strip().rstrip('。.') or '检索结果不足'}。"
                "如果这是学习重点，建议在「学习资源」里找对应的课程补充。"
            ),
            answered_by_general_model=True,
        )

    @staticmethod
    def _build_general_prompt(agent_input: MaterialQaAgentInput) -> str:
        history = "\n".join(
            f"{'用户' if message.role == 'user' else '助手'}：{message.content}"
            for message in agent_input.history
        ) or "（无历史对话）"

        return f"""你是一位耐心的学习助教。当前问题在学习者的教材里没有找到依据，学习者已经知道这一点，并明确要求你用通用知识回答。

请遵守：
1. 用你自己的通用知识作答，中文，条理清晰，必要时分点。
2. 不要声称任何内容来自学习者的教材，不要编造章节号、页码或引用。
3. 对存在争议或你不确定的部分，明确说明不确定。
4. 只输出一个合法 JSON 对象，不要使用 Markdown 代码块。格式必须是：
{{"refused": false, "answer": "你的回答"}}

历史对话：
{history}

当前问题：
{agent_input.current_question}
"""

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
