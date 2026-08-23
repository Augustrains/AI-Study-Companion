"""Manual live smoke test for the complete memory-to-plan flow."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

from modules.diagnosis.agent import DiagnosticAgent
from modules.common.knowledge_points import JsonKnowledgePointCatalog
from modules.diagnosis.services import AssessmentService, DiagnosisResultStore, GeneratedQuestionBank
from modules.diagnosis.workflow import DiagnosisWorkflow
from modules.learner_profile.models import LearnerProfile, LearningPreferences
from modules.learning_plan.agent import LearningPlanAgent
from modules.learning_plan.module import LearningPlanModule
from modules.memory.models import EvidenceSummary, KnowledgePointMemory, LearnerMemory
from modules.memory.module import MemoryModule
from modules.memory.repository import JsonMemoryRepository
from sdk.llm_client import DeepSeekLLMClient, LLMClient
from tests.test_support import test_directory


PROJECT_DIR = Path(__file__).resolve().parents[1]


def live_client() -> DeepSeekLLMClient:
    return replace(DeepSeekLLMClient.from_env(), timeout=120.0)


class CapturingClient:
    def __init__(self, delegate: LLMClient) -> None:
        self.delegate = delegate
        self.call_count = 0
        self.last_response = ""
        self.last_error = ""

    def generate(self, prompt: str) -> str:
        self.call_count += 1
        try:
            self.last_response = self.delegate.generate(prompt)
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            raise
        return self.last_response


class ProfileStub:
    def get(self, user_id: str, learning_domain: str) -> LearnerProfile:
        return LearnerProfile(
            user_id=user_id,
            learning_domain=learning_domain,
            preferences=LearningPreferences(session_duration_minutes=15),
        )


def main() -> None:
    with test_directory("live-full-learning-flow") as directory:
        memory_repository = JsonMemoryRepository(directory / "memory.json")
        memory_repository.upsert(
            LearnerMemory(
                user_id="live-flow-user",
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
        results = DiagnosisResultStore()
        diagnostic_client = CapturingClient(live_client())
        diagnosis = DiagnosisWorkflow(
            question_bank=GeneratedQuestionBank(PROJECT_DIR / "data" / "question_new"),
            result_store=results,
            assessment_service=AssessmentService(),
            diagnostic_agent=DiagnosticAgent(diagnostic_client),
            memory=memory,
            knowledge_point_catalog=JsonKnowledgePointCatalog(PROJECT_DIR / "data" / "question_new" / "知识点"),
        )

        started = diagnosis.start_diagnosis(
            user_id="live-flow-user",
            book_id="ml-001",
            learning_goal="理解回归数据并复习线性与多项式回归",
        )
        questions = started["questions"]
        if not questions:
            raise RuntimeError("live planning model selected no questions")
        print(f"question_planning_llm_calls={diagnostic_client.call_count}")
        print(f"question_planning_model_response_chars={len(diagnostic_client.last_response)}")
        print(f"selected_questions={len(questions)}")
        print(f"selected_knowledge_points={sorted({item['tag'] for item in questions})}")

        for question in questions:
            diagnosis.submit_answer(
                started["diagnostic_id"], question["id"], question["options"][0]["id"]
            )

        summary = asyncio.run(diagnosis.finish_diagnosis(started["diagnostic_id"]))
        diagnosis.confirm_diagnosis(
            started["diagnostic_id"],
            calibration="same",
            reason="本次结果基本符合我的实际感受。",
        )
        print(f"diagnostic_accuracy={summary['accuracy']}")
        print(f"diagnostic_level={summary['level']}")

        plan_client = CapturingClient(live_client())
        plan_module = LearningPlanModule(
            results,
            LearningPlanAgent(plan_client),
            path=directory / "plans.json",
            memory=memory,
            learner_profile=ProfileStub(),
        )
        plan = plan_module.generate(
            diagnostic_id=started["diagnostic_id"],
            book_id="ml",
            goal="理解回归数据并复习线性与多项式回归",
        )
        if not plan["tasks"]:
            raise RuntimeError("live planning model produced no tasks and fallback was empty")
        if not plan_client.last_response:
            raise RuntimeError(f"learning plan model fell back without a response: {plan_client.last_error}")
        if any(int(task["minutes"]) > 15 for task in plan["tasks"]):
            raise RuntimeError("generated task exceeded the learner time budget")
        print(f"learning_plan_llm_calls={plan_client.call_count}")
        print(f"learning_plan_model_response_chars={len(plan_client.last_response)}")
        print(f"generated_tasks={len(plan['tasks'])}")
        for task in plan["tasks"]:
            print(f"task={task['title']} | type={task['type']} | minutes={task['minutes']}")
        print(f"advice_count={len(plan['advice'])}")
        print("live_flow=passed")


if __name__ == "__main__":
    main()
