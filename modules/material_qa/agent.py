"""资料问答 Agent。"""

from __future__ import annotations

import json

from modules.common.errors import AppError
from sdk.llm_client import LLMClient, NullLLMClient

from .models import MaterialQaAgentInput, MaterialQaAgentOutput, MaterialQaMessage


def _first_json_object(raw_response: str) -> dict | None:
    """Extract the first JSON object even when a model repeats its output."""

    content = raw_response.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            content = "\n".join(lines[1:-1]).strip()

    decoder = json.JSONDecoder()
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, str):
            content = parsed.strip()
    except json.JSONDecodeError:
        pass

    # raw_decode intentionally permits trailing text. Scanning also handles a
    # malformed preface followed by a valid object.
    for index, character in enumerate(content):
        if character != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(content, index)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None

########## 这部分是在发现一些代词之后，利用LLM来修改向量检索的内容
class MaterialQaQueryRewriter:
    """Turn a contextual follow-up into one standalone retrieval question."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or NullLLMClient()

    def rewrite(self, *, history: list[MaterialQaMessage], question: str) -> str:
        question = question.strip()
        if not history:
            return question
        try:
            raw_response = self.llm_client.generate(self._build_prompt(history=history, question=question))
        except AppError:
            # Rewriting is an optimization. A failure must not prevent the main QA call.
            return question
        return self._parse_response(raw_response, fallback=question)

    @staticmethod
    def _build_prompt(*, history: list[MaterialQaMessage], question: str) -> str:
        recent_history = "\n".join(
            f"{'用户' if message.role == 'user' else '助手'}：{message.content.strip()[:500]}"
            for message in history[-6:]
            if message.content.strip()
        ) or "（无历史对话）"
        return f"""你是资料检索问题改写器。你的任务不是回答问题，而是输出一条可独立用于向量检索的问题。

规则：
1. 如果当前问题包含“它”“这个”“上述内容”等指代或省略信息，只补全历史中明确对应的对象。
2. 如果当前问题本身已经完整、与上一话题无关，必须原样保留，不得混入历史话题。
3. 不得增加用户没有询问的新主题，不得回答问题。
4. 只输出合法 JSON：{{"standaloneQuestion": "改写后的问题"}}

历史对话：
{recent_history}

当前问题：
{question}
"""

    @staticmethod
    def _parse_response(raw_response: str, *, fallback: str) -> str:
        try:
            rewritten = (_first_json_object(raw_response) or {})["standaloneQuestion"]
        except (KeyError, TypeError):
            return fallback
        if not isinstance(rewritten, str) or not rewritten.strip():
            return fallback
        return rewritten.strip()

########## """使用对话历史和 RAG 检索上下文生成资料问答回答。"""
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

        payload = _first_json_object(raw_response)
        try:
            if payload is None:
                raise ValueError("missing material QA JSON object")
            answer = payload["answer"]
            refused = payload["refused"]
            if not isinstance(answer, str) or not answer.strip() or not isinstance(refused, bool):
                raise ValueError("invalid material QA response fields")
            return answer.strip(), refused
        except (KeyError, TypeError, ValueError):
            return "模型返回格式异常，请重新发送本轮问题。", True

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

        teaching_strategy = ""
        if agent_input.answer_mode == "socratic":
            teaching_strategy = f"""

当前启用了“苏格拉底引导作答”模式。
原始学习任务：{agent_input.root_question or agent_input.current_question}
当前教学状态：{agent_input.socratic_state or 'probe'}
本轮教学指令：{agent_input.socratic_directive}

引导模式规则：
- 严格执行本轮教学指令，并以教材资料为事实依据。
- 除非教学指令明确要求直接讲解，否则不要直接给出原始任务的完整答案。
- 每轮最多提出一个核心问题，内容应短而具体，让学习者能够立即回答。
- 可以先用一两句话反馈学习者上一轮的思路，再提出本轮问题。
- 不要向学习者展示状态名、回答质量标签或内部决策过程。
"""

        return f"""你是 Study Companion 的资料问答助手。请严格遵守以下规则：
1. 先结合历史对话理解当前问题中的“这个”“它”“上述内容”等指代和省略信息。
2. 历史对话只用于确定当前问题所指的对象；事实性回答仍须优先依据给出的检索资料，不要编造资料中没有的事实。
3. 使用清晰、准确、适合学习者理解的中文；必要时分点说明。
4. 如果资料不足以回答，应明确说明资料不足，并指出还需要什么信息。
5. 当问题与资料无关，或资料不足以可靠回答时，将 refused 设为 true，并在 answer 中简要说明拒答原因。
6. 只有回答能够由检索资料直接支持时，才将 refused 设为 false。
7. 只输出一次、一个合法 JSON 对象，生成对象后立即停止；不要重复输出，不要使用 Markdown 代码块，不要输出思考过程或其他文字。格式必须是：
{{"refused": false, "answer": "基于资料的最终回答"}}
{teaching_strategy}

历史对话：
{history}

检索资料：
{context}

当前问题：
{agent_input.current_question}
"""
