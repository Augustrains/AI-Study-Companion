import json
import unittest

from modules.diagnosis.agent import DiagnosticAgent, QuestionPlanningInput


class RecordingLLMClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompt = ""

    def generate(self, prompt: str) -> str:
        self.prompt = prompt
        return self.response


class DiagnosticQuestionPlanningTest(unittest.TestCase):
    def test_agent_uses_llm_count_and_type_with_backend_bounds(self) -> None:
        client = RecordingLLMClient(
            json.dumps(
                {
                    "selections": [
                        {
                            "knowledgePointId": "linear_regression",
                            "questionCount": 9,
                            "taskMode": "independent",
                        },
                        {
                            "knowledgePointId": "supervised_learning",
                            "questionCount": 0,
                            "taskMode": "retrieval",
                        },
                    ]
                }
            )
        )
        planning_input = QuestionPlanningInput(
            learning_goal="理解机器学习基础",
            knowledge_point_mastery={"linear_regression": "了解", "supervised_learning": "掌握"},
            knowledge_point_review={"supervised_learning": {"next_review_at": "2000-01-01T00:00:00+00:00"}},
            available_question_counts={"linear_regression": 3, "supervised_learning": 2},
        )

        plan = DiagnosticAgent(client).plan_questions(planning_input)

        self.assertEqual(
            [(item.knowledge_point_id, item.question_count, item.task_mode) for item in plan],
            [("linear_regression", 3, "independent"), ("supervised_learning", 0, "retrieval")],
        )
        self.assertIn("理解机器学习基础", client.prompt)
        self.assertIn("availableQuestionCount", client.prompt)
        self.assertNotIn("difficulty", client.prompt)

    def test_empty_llm_response_uses_mastery_based_fallback(self) -> None:
        plan = DiagnosticAgent(RecordingLLMClient("")).plan_questions(
            QuestionPlanningInput(
                learning_goal="",
                knowledge_point_mastery={"known": "掌握"},
                knowledge_point_review={},
                available_question_counts={"unknown": 7, "known": 3},
            )
        )

        self.assertEqual(
            [(item.knowledge_point_id, item.question_count, item.task_mode) for item in plan],
            [("unknown", 4, "diagnostic"), ("known", 1, "challenge")],
        )

    def test_retrieval_is_rejected_when_review_is_not_due(self) -> None:
        client = RecordingLLMClient(
            '{"selections":[{"knowledgePointId":"known","questionCount":1,"taskMode":"retrieval"}]}'
        )
        plan = DiagnosticAgent(client).plan_questions(
            QuestionPlanningInput(
                learning_goal="巩固知识",
                knowledge_point_mastery={"known": "掌握"},
                knowledge_point_review={"known": {"next_review_at": "2999-01-01T00:00:00+00:00"}},
                available_question_counts={"known": 2},
            )
        )

        self.assertEqual(plan[0].task_mode, "challenge")

    def test_total_question_count_is_bounded(self) -> None:
        selections = [
            {
                "knowledgePointId": f"point-{index}",
                "questionCount": 4,
                "taskMode": "diagnostic",
            }
            for index in range(5)
        ]
        plan = DiagnosticAgent(RecordingLLMClient(json.dumps({"selections": selections}))).plan_questions(
            QuestionPlanningInput(
                learning_goal="聚焦薄弱知识点",
                knowledge_point_mastery={},
                knowledge_point_review={},
                available_question_counts={f"point-{index}": 6 for index in range(5)},
            )
        )

        self.assertEqual(sum(item.question_count for item in plan), DiagnosticAgent.MAX_TOTAL_QUESTIONS)

    def test_catalog_metadata_filters_unrelated_unseen_points(self) -> None:
        client = RecordingLLMClient(
            json.dumps(
                {
                    "selections": [
                        {"knowledgePointId": "regression-data", "questionCount": 2, "taskMode": "diagnostic"},
                        {"knowledgePointId": "classification", "questionCount": 2, "taskMode": "diagnostic"},
                    ]
                }
            )
        )
        plan = DiagnosticAgent(client).plan_questions(
            QuestionPlanningInput(
                learning_goal="理解回归数据并完成可视化",
                knowledge_point_mastery={},
                knowledge_point_review={},
                available_question_counts={"regression-data": 6, "classification": 6},
                knowledge_point_catalog={
                    "regression-data": {
                        "name": "回归数据准备与可视化",
                        "description": "完成回归数据清洗、探索和可视化。",
                    },
                    "classification": {
                        "name": "分类实践",
                        "description": "训练分类器并评估分类结果。",
                    },
                },
            )
        )

        self.assertEqual([item.knowledge_point_id for item in plan], ["regression-data"])
        self.assertIn("回归数据准备与可视化", client.prompt)
        self.assertNotIn('"knowledgePointId": "classification"', client.prompt)

if __name__ == "__main__":
    unittest.main()
