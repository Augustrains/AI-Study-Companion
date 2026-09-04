import unittest

from modules.material_qa.agent import MaterialQaAgent
from modules.material_qa.models import (
    MaterialQaAgentInput,
    MaterialQaMessage,
    MaterialQaRetrievedChunk,
    MaterialQaRetrievalResult,
)
from modules.material_qa.schemas import MaterialQaSource


class RecordingLLMClient:
    def __init__(self, answer: str = '{"refused": false, "answer": "模型回答"}') -> None:
        self.answer = answer
        self.prompt = ""

    def generate(self, prompt: str) -> str:
        self.prompt = prompt
        return self.answer


class MaterialQaAgentTest(unittest.TestCase):
    def test_generate_calls_llm_with_history_question_and_retrieval(self):
        client = RecordingLLMClient()
        source = MaterialQaSource(
            id="source-1",
            type="教材",
            title="模型评估",
            location="第 4 章",
            excerpt="验证误差可用于观察泛化能力。",
            knowledgePointIds=["overfitting", "model-evaluation"],
        )
        agent_input = MaterialQaAgentInput(
            history=[MaterialQaMessage(role="user", content="什么是训练误差？")],
            current_question="如何判断过拟合？",
            retrieval=MaterialQaRetrievalResult(
                chunks=[MaterialQaRetrievedChunk(text="训练误差下降而验证误差上升时可能过拟合。", source=source, score=0.9)]
            ),
        )

        output = MaterialQaAgent(client).generate(agent_input)

        self.assertEqual(output.answer, "模型回答")
        self.assertFalse(output.refused)
        self.assertEqual(output.citations, [source])
        self.assertEqual(output.related_knowledge_points, ["model-evaluation", "overfitting"])
        self.assertIn("什么是训练误差？", client.prompt)
        self.assertIn("如何判断过拟合？", client.prompt)
        self.assertIn("[资料1] 模型评估（第 4 章）", client.prompt)
        self.assertIn("训练误差下降而验证误差上升", client.prompt)

    def test_refusal_hides_citations_and_related_knowledge_points(self):
        client = RecordingLLMClient('{"refused": true, "answer": "当前资料无法回答该问题。"}')
        source = MaterialQaSource(
            id="source-1",
            type="教材",
            title="模型评估",
            location="第 4 章",
            excerpt="验证误差用于评估模型。",
            knowledgePointIds=["model-evaluation"],
        )
        agent_input = MaterialQaAgentInput(
            history=[],
            current_question="请给出红烧肉配方",
            retrieval=MaterialQaRetrievalResult(
                chunks=[MaterialQaRetrievedChunk(text="验证误差用于评估模型。", source=source, score=0.2)]
            ),
        )

        output = MaterialQaAgent(client).generate(agent_input)

        self.assertTrue(output.refused)
        self.assertEqual(output.answer, "当前资料无法回答该问题。")
        self.assertEqual(output.citations, [])
        self.assertEqual(output.related_knowledge_points, [])

    def test_invalid_structured_output_fails_closed_without_citations(self):
        client = RecordingLLMClient("未按 JSON 格式返回的回答")
        agent_input = MaterialQaAgentInput(
            history=[],
            current_question="问题",
            retrieval=MaterialQaRetrievalResult(chunks=[]),
        )

        output = MaterialQaAgent(client).generate(agent_input)

        self.assertTrue(output.refused)
        self.assertEqual(output.citations, [])

    def test_repeated_json_output_uses_first_object_without_leaking_json(self):
        client = RecordingLLMClient(
            '{"refused": false, "answer": "先想一想训练集和测试集的差别。"}'
            '{"refused": false, "answer": "重复内容"}'
        )
        agent_input = MaterialQaAgentInput(
            history=[],
            current_question="我不知道",
            retrieval=MaterialQaRetrievalResult(chunks=[]),
            answer_mode="socratic",
            socratic_state="scaffold",
        )

        output = MaterialQaAgent(client).generate(agent_input)

        self.assertEqual(output.answer, "先想一想训练集和测试集的差别。")
        self.assertNotIn("refused", output.answer)


if __name__ == "__main__":
    unittest.main()
