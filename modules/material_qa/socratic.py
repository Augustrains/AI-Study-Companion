"""State machine and assessment helpers for Socratic material tutoring."""

from __future__ import annotations

import json
from dataclasses import dataclass

from modules.common.errors import AppError
from sdk.llm_client import LLMClient, NullLLMClient

from .models import ResponseQuality, SocraticStateName

##### 定义状态转移表("当前状态", "学生回答质量"): "下一个状态"
_TRANSITIONS: dict[tuple[SocraticStateName, ResponseQuality], SocraticStateName] = {
    ("probe", "correct"): "confirm",
    ("probe", "partial"): "clarify",
    ("probe", "wrong"): "confront",
    ("probe", "confused"): "scaffold",
    ("probe", "no_response"): "scaffold",
    ("clarify", "correct"): "confirm",
    ("clarify", "partial"): "scaffold",
    ("clarify", "wrong"): "confront",
    ("clarify", "confused"): "scaffold",
    ("clarify", "no_response"): "scaffold",
    ("confront", "correct"): "confirm",
    ("confront", "partial"): "clarify",
    ("confront", "wrong"): "scaffold",
    ("confront", "confused"): "scaffold",
    ("confront", "no_response"): "scaffold",
    ("scaffold", "correct"): "confirm",
    ("scaffold", "partial"): "clarify",
    ("scaffold", "wrong"): "scaffold",
    ("scaffold", "confused"): "scaffold",
    ("scaffold", "no_response"): "scaffold",
    ("confirm", "correct"): "confirm",
    ("confirm", "partial"): "clarify",
    ("confirm", "wrong"): "clarify",
    ("confirm", "confused"): "scaffold",
    ("confirm", "no_response"): "scaffold",
}
##### 五种教学状态
_DIRECTIVES: dict[SocraticStateName, str] = {
    "probe": "先探测学习者已有理解。只提出一个开放式引导问题，不直接给出答案。",
    "clarify": "学习者的理解还不完整或较模糊。只提出一个更具体的问题，定位其已理解和未理解的部分。",
    "confront": "学习者可能存在误解。给出一个简短反例或矛盾情境，再提出一个问题让其自行发现冲突；不要直接说‘你错了’。",
    "scaffold": "学习者目前卡住了。只提供一个小提示，把问题拆成更小的一步，并以一个可回答的问题结尾；不要泄露完整答案。",
    "confirm": "学习者已经接近掌握。提出一个稍有变化的迁移问题，验证其能否把同一原理用于新情境。",
}


@dataclass
class SocraticEngine:
    state: SocraticStateName = "probe"
    turns_in_state: int = 0

    MAX_SCAFFOLD_TURNS = 4

    def transition(self, quality: ResponseQuality) -> SocraticStateName:
        next_state = _TRANSITIONS.get((self.state, quality), "scaffold")
        self.turns_in_state = self.turns_in_state + 1 if next_state == self.state else 0
        self.state = next_state
        return self.state

    @property
    def directive(self) -> str:
        if self.state == "scaffold" and self.turns_in_state >= self.MAX_SCAFFOLD_TURNS:
            return (
                "学习者已经连续多轮卡住。现在给出简明的直接讲解和一个贴近原题的示例，"
                "但不要替学习者完成整道题；最后提出一个简单问题检查理解。"
            )
        return _DIRECTIVES[self.state]

#### 评估学习者的本轮学习情况
class MaterialQaResponseClassifier:
    """Classify a learner reply before selecting the next teaching action."""

    VALID: set[str] = {"correct", "partial", "wrong", "confused", "no_response"}

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or NullLLMClient()

    def classify(
        self,
        *,
        root_question: str,
        tutor_message: str,
        learner_message: str,
        material_context: str,
    ) -> ResponseQuality:
        prompt = f"""你是教学回答评估器。结合原始学习任务、导师上一问和教材依据，判断学习者本轮回答质量。

只能从以下五个标签中选择：
- correct：回答正确且表现出理解
- partial：方向正确但不完整或表述模糊
- wrong：结论错误或存在概念误解
- confused：明确表示不会、困惑或请求提示
- no_response：答非所问、回避或信息少到无法判断

原始学习任务：{root_question[:1000]}
导师上一问：{tutor_message[:800]}
学习者回答：{learner_message[:800]}
教材依据：{material_context[:2500] or '未检索到教材依据'}

只输出合法 JSON：{{"quality":"partial"}}"""
        try:
            response = self.llm_client.generate(prompt).strip()
            if response.startswith("```") and response.endswith("```"):
                response = "\n".join(response.splitlines()[1:-1]).strip()
            quality = json.loads(response).get("quality")
            if quality in self.VALID:
                return quality
        except (AppError, json.JSONDecodeError, AttributeError, TypeError):
            pass
        return "partial"
