import asyncio
import json
from pathlib import Path

from modules.diagnosis.agent import DiagnosticAgent
from modules.diagnosis.services import AssessmentService, DiagnosticSessionStore, GeneratedQuestionBank
from modules.diagnosis.workflow import DiagnosisWorkflow
from modules.common.knowledge_points import JsonKnowledgePointCatalog
from modules.learner_profile.models import LearnerProfile, LearningPreferences
from modules.learning_plan.agent import LearningPlanAgent
from modules.learning_plan.module import LearningPlanModule
from modules.memory.models import EvidenceSummary, KnowledgePointMemory, LearnerMemory
from modules.memory.module import MemoryModule
from modules.memory.repository import JsonMemoryRepository
from tests.test_support import test_directory


PROJECT_DIR = Path(__file__).resolve().parents[1]


class DiagnosticPlanningLLM:
    def __init__(self) -> None:
        self.prompt = ""

    def generate(self, prompt: str) -> str:
        self.prompt = prompt
        raw_points = prompt.split("候选知识点：", 1)[1].split("\n\n输出格式", 1)[0]
        points = json.loads(raw_points)
        selections = []
        for point in points:
            point_id = point["knowledgePointId"]
            count = 1 if point_id in {"kp-ml-regression-data", "kp-ml-linear-polynomial-regression"} else 0
            selections.append(
                {
                    "knowledgePointId": point_id,
                    "questionCount": min(count, point["availableQuestionCount"]),
                    "taskMode": "remediation" if point_id == "kp-ml-regression-data" else "independent",
                }
            )
        return json.dumps({"selections": selections}, ensure_ascii=False)


class PlanGeneratingLLM:
    def __init__(self) -> None:
        self.prompt = ""

    def generate(self, prompt: str) -> str:
        self.prompt = prompt
        context = json.loads(prompt.split("输入：\n", 1)[1])
        tasks = [
            {
                "abilityId": unit["ability_id"],
                "title": f"强化{unit['ability_id']}",
                "type": "concept_review" if index == 0 else "practice",
                "minutes": 30,
                "reason": f"本轮该能力答对 {unit['correct']}/{unit['total']} 题。",
                "description": "先复盘错题对应概念，再完成一次针对性练习。",
            }
            for index, unit in enumerate(context["abilityUnits"])
        ]
        return json.dumps({"tasks": tasks, "advice": ["优先处理本轮暴露的薄弱知识点。"]}, ensure_ascii=False)


class ProfileStub:
    def get(self, user_id: str, learning_domain: str) -> LearnerProfile:
        return LearnerProfile(
            user_id=user_id,
            learning_domain=learning_domain,
            preferences=LearningPreferences(session_duration_minutes=15),
        )


def test_memory_to_questions_to_calibrated_ai_plan() -> None:
    with test_directory("full-learning-flow") as directory:
        memory_repository = JsonMemoryRepository(directory / "memory.json")
        memory_repository.upsert(
            LearnerMemory(
                user_id="flow-user",
                learning_domain="ml-001",
                knowledge_points=[
                    KnowledgePointMemory(
                        knowledge_point_id="kp-ml-regression-data",
                        mastery_level="不会",
                        mastery_score=0.12,
                        confidence=0.4,
                        evidence_summary=EvidenceSummary(accepted_evidence_count=2),
                    ),
                    KnowledgePointMemory(
                        knowledge_point_id="kp-ml-linear-polynomial-regression",
                        mastery_level="熟悉",
                        mastery_score=0.68,
                        confidence=0.7,
                        evidence_summary=EvidenceSummary(accepted_evidence_count=4),
                    ),
                ],
            )
        )
        memory = MemoryModule(memory_repository)
        sessions = DiagnosticSessionStore()
        diagnostic_llm = DiagnosticPlanningLLM()
        diagnosis = DiagnosisWorkflow(
            question_bank=GeneratedQuestionBank(PROJECT_DIR / "data" / "question_new"),
            session_store=sessions,
            assessment_service=AssessmentService(),
            diagnostic_agent=DiagnosticAgent(diagnostic_llm),
            memory=memory,
            knowledge_point_catalog=JsonKnowledgePointCatalog(PROJECT_DIR / "data" / "question_new" / "知识点"),
        )

        started = diagnosis.start_diagnosis(
            user_id="flow-user",
            book_id="ml-001",
            learning_goal="理解过拟合并复习线性回归",
        )
        assert started["questions"]
        assert '"mastery": "不会"' in diagnostic_llm.prompt
        assert '"mastery_score": 0.12' in diagnostic_llm.prompt

        session = sessions.get(started["diagnostic_id"])
        for index, question in enumerate(session.questions):
            expected = session.correct_answers[question["id"]]
            submitted = expected
            if index == 0:
                submitted = next(option["id"] for option in question["options"] if option["id"] != expected)
            diagnosis.submit_answer(session.id, question["id"], submitted)

        summary = asyncio.run(diagnosis.finish_diagnosis(session.id))
        assert summary["accuracy"].endswith("%")
        finalized = diagnosis.confirm_diagnosis(
            session.id,
            calibration="higher",
            reason="我有实际使用经验，但第一题审题失误。",
        )
        assert finalized is not None
        assert sessions.get(session.id).calibration_reason == "我有实际使用经验，但第一题审题失误。"

        plan_llm = PlanGeneratingLLM()
        plan_module = LearningPlanModule(
            sessions,
            LearningPlanAgent(plan_llm),
            path=directory / "plans.json",
            memory=memory,
            learner_profile=ProfileStub(),
        )
        plan = plan_module.generate(
            diagnostic_id=session.id,
            book_id="ml",
            goal="理解过拟合并复习线性回归",
        )

        assert plan["tasks"]
        assert all(task["minutes"] <= 15 for task in plan["tasks"])
        assert "我有实际使用经验，但第一题审题失误。" in plan_llm.prompt
        assert '"sessionTimeBudgetMinutes": 15' in plan_llm.prompt
        assert '"questionEvidence"' in plan_llm.prompt
        updated_memory = memory.get_learner_memory("flow-user", "ml-001")
        assert updated_memory.diagnosis_summary["diagnostic_id"] == session.id
