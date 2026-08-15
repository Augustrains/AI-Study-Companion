import json

from modules.diagnosis.models import DiagnosticSession
from modules.diagnosis.services import DiagnosticSessionStore
from modules.learning_plan.agent import LearningPlanAgent, LearningPlanAgentInput
from modules.learning_plan.module import LearningPlanModule
from modules.learning_plan.schemas import GenerateLearningPlanResponse
from modules.learner_profile.models import LearnerProfile, LearningPreferences
from tests.test_support import test_directory


class RecordingLLMClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompt = ""

    def generate(self, prompt: str) -> str:
        self.prompt = prompt
        return self.response


class StubLearnerProfileWorkflow:
    def get(self, user_id: str, learning_domain: str) -> LearnerProfile:
        assert user_id == "user-1"
        assert learning_domain == "machine_learning"
        return LearnerProfile(
            user_id=user_id,
            learning_domain=learning_domain,
            preferences=LearningPreferences(session_duration_minutes=12),
        )


def fallback_task() -> dict:
    return {
        "id": "diag-1-ability-conceptual",
        "title": "提升概念理解能力",
        "type": "concept_review",
        "source": "diagnostic",
        "minutes": 25,
        "status": "in_progress",
        "reason": "诊断结果为“不会”，答对 0/1 题",
        "description": "复习关联知识点并完成练习。",
        "learning_goal": "理解过拟合",
        "ability_id": "conceptual",
        "knowledge_point_ids": ["overfitting"],
        "chapter_ids": ["chapter-1"],
        "question_ids": ["q1"],
    }


def agent_input() -> LearningPlanAgentInput:
    return LearningPlanAgentInput(
        book={"id": "ml", "title": "《机器学习》", "shortTitle": "机器学习"},
        goal="理解过拟合",
        goal_level="了解核心概念",
        diagnostic_summary={"accuracy": 0.0, "totalQuestions": 1},
        knowledge_point_results=[
            {
                "knowledgePointId": "overfitting",
                "knowledgePointName": "过拟合与泛化",
                "effectiveMasteryLevel": "不会",
                "roundCorrect": 0,
                "roundTotal": 1,
            }
        ],
        ability_units=[{"ability_id": "conceptual", "status": "不会"}],
        question_evidence=[
            {
                "questionId": "q1",
                "title": "什么现象表示过拟合？",
                "submittedAnswerText": "训练误差下降",
                "correctAnswerText": "训练误差下降但验证误差上升",
                "outcome": "incorrect",
            }
        ],
        constraints={
            "allowedTaskTypes": ["concept_review", "practice", "retest"],
            "minTaskMinutes": 5,
            "maxTaskMinutes": 60,
        },
    )


def test_agent_uses_llm_task_wording_but_preserves_backend_owned_fields() -> None:
    client = RecordingLLMClient(
        json.dumps(
            {
                "tasks": [
                    {
                        "abilityId": "conceptual",
                        "title": "辨析过拟合信号",
                        "type": "practice",
                        "minutes": 18,
                        "reason": "用户混淆了训练表现与泛化表现。",
                        "description": "先对比训练误差和验证误差，再完成两道判断练习。",
                    }
                ],
                "advice": ["先修复概念混淆，再进行复测。"],
            },
            ensure_ascii=False,
        )
    )

    plan = LearningPlanAgent(client).build(agent_input(), fallback_tasks=[fallback_task()])

    assert plan["tasks"][0]["title"] == "辨析过拟合信号"
    assert plan["tasks"][0]["type"] == "practice"
    assert plan["tasks"][0]["id"] == "diag-1-ability-conceptual"
    assert plan["tasks"][0]["knowledge_point_ids"] == ["overfitting"]
    assert plan["tasks"][0]["status"] == "in_progress"
    assert plan["advice"] == ["先修复概念混淆，再进行复测。"]
    assert "训练误差下降但验证误差上升" in client.prompt


def test_agent_invalid_json_falls_back_to_deterministic_plan() -> None:
    plan = LearningPlanAgent(RecordingLLMClient("not-json")).build(
        agent_input(), fallback_tasks=[fallback_task()]
    )

    assert plan["tasks"][0]["title"] == "提升概念理解能力"
    assert plan["advice"][0].startswith("诊断正确率为 0%")


def test_learning_plan_module_sends_derived_diagnosis_context_to_agent() -> None:
    client = RecordingLLMClient(
        '{"tasks":[{"abilityId":"conceptual","title":"修复过拟合概念",'
        '"type":"concept_review","minutes":20,"reason":"该题回答错误",'
        '"description":"阅读关联内容并重新解释正确答案"}],"advice":["完成后进行复测。"]}'
    )
    store = DiagnosticSessionStore()
    session = DiagnosticSession(
        id="diag-1",
        user_id="user-1",
        book_id="ml-001",
        learning_goal="理解过拟合",
        status="completed",
        calibration="higher",
        calibration_reason="我在项目中使用过这个概念，但本轮题目理解有偏差。",
        questions=[
            {
                "id": "q1",
                "title": "什么现象表示过拟合？",
                "tag": "overfitting",
                "knowledge_point_ids": ["overfitting"],
                "ability_ids": ["conceptual"],
                "chapter_id": "chapter-1",
                "section_ids": ["section-1"],
                "task_mode": "diagnostic",
                "source": "lessons/overfitting.md",
                "options": [
                    {"id": "A", "text": "训练误差下降"},
                    {"id": "B", "text": "训练误差下降但验证误差上升"},
                ],
            }
        ],
        answers={"q1": "A"},
        correct_answers={"q1": "B"},
        result={
            "results": [
                {
                    "knowledge_point_id": "overfitting",
                    "ai_status": "不会",
                    "calibrated_status": "了解",
                    "correct": 0,
                    "total": 1,
                    "mastery_score": 0.0,
                    "confidence": 0.22,
                    "memory_status": "未验证",
                    "memory_stability_days": 0.0,
                    "next_review_at": None,
                    "evidence_summary": {},
                    "reason_codes": [],
                }
            ],
            "answer_records": [
                {
                    "question_id": "q1",
                    "submitted_answer": "A",
                    "correct_answer": "B",
                    "is_correct": False,
                    "skipped": False,
                    "knowledge_point_ids": ["overfitting"],
                }
            ],
        },
    )
    store.save(session)

    with test_directory("learning-plan-agent") as directory:
        module = LearningPlanModule(
            store,
            LearningPlanAgent(client),
            path=directory / "plans.json",
            learner_profile=StubLearnerProfileWorkflow(),
        )
        plan = module.generate(diagnostic_id="diag-1", book_id="ml", goal="理解过拟合")

    response = GenerateLearningPlanResponse.model_validate(plan)
    assert response.tasks[0].title == "修复过拟合概念"
    assert response.tasks[0].minutes == 12
    assert response.tasks[0].knowledge_point_ids == ["overfitting"]
    assert response.resources[0].location == "lessons/overfitting.md"
    assert '"userCalibratedLevel": "了解"' in client.prompt
    assert '"submittedAnswerText": "训练误差下降"' in client.prompt
    assert '"correctAnswerText": "训练误差下降但验证误差上升"' in client.prompt
    assert '"sessionTimeBudgetMinutes": 12' in client.prompt
    assert "我在项目中使用过这个概念，但本轮题目理解有偏差。" in client.prompt
