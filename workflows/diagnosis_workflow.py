from typing import Any
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agents.diagnostic_agent import DiagnosticAgent
from domain.assessment_service import AssessmentService
from domain.models import DiagnosisResult, KnowledgePointResult, LearningSession
from repositories.question_repository import QuestionRepository
from repositories.session_repository import InMemoryLearningSessionRepository
from workflows.diagnosis_graph import build_diagnosis_graph


class DiagnosisWorkflow:
    """诊断流程门面；对外隐藏 LangGraph 的暂停与恢复细节。"""

    def __init__(
        self,
        question_repository: QuestionRepository,
        session_repository: InMemoryLearningSessionRepository,
        assessment_service: AssessmentService,
        diagnostic_agent: DiagnosticAgent,
        checkpointer: Any | None = None,
    ) -> None:
        self.session_repository = session_repository
        self.checkpointer = checkpointer or InMemorySaver()
        self.graph = build_diagnosis_graph(
            question_repository=question_repository,
            session_repository=session_repository,
            assessment_service=assessment_service,
            diagnostic_agent=diagnostic_agent,
            checkpointer=self.checkpointer,
        )

    @staticmethod
    def _config(diagnosis_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": diagnosis_id}}

    @staticmethod
    def _interrupt_value(result: dict[str, Any]) -> dict[str, Any]:
        interrupts = result.get("__interrupt__", ())
        if not interrupts:
            raise RuntimeError("工作流没有在预期位置暂停")
        return interrupts[0].value

    def start(self, session: LearningSession) -> dict[str, Any]:
        diagnosis_id = f"diag_{uuid4().hex[:8]}"
        self.session_repository.save(session)
        result = self.graph.invoke(
            {
                "workflow_run_id": diagnosis_id,
                "diagnosis_id": diagnosis_id,
                "learning_session_id": session.id,
                "user_id": session.user_id,
                "book_id": session.book_id,
                "learning_goal": session.learning_goal,
                "status": "started",
            },
            config=self._config(diagnosis_id),
        )
        return self._interrupt_value(result)

    def submit(
        self, diagnosis_id: str, answers: dict[str, str]
    ) -> dict[str, Any]:
        """提交答案，运行到人工确认节点并返回诊断草稿。"""
        result = self.graph.invoke(
            Command(resume=answers),
            config=self._config(diagnosis_id),
        )
        return self._interrupt_value(result)

    def review(
        self,
        diagnosis_id: str,
        *,
        action: str = "approve",
        calibrations: dict[str, str] | None = None,
    ) -> DiagnosisResult | None:
        """确认、修改或拒绝诊断；批准后才正式写入 LearningSession。"""
        result = self.graph.invoke(
            Command(
                resume={
                    "action": action,
                    "calibrations": calibrations or {},
                }
            ),
            config=self._config(diagnosis_id),
        )
        if result["status"] == "rejected":
            return None

        state = self.graph.get_state(self._config(diagnosis_id)).values
        results = [
            KnowledgePointResult(**item) for item in state["draft_results"]
        ]
        for item in results:
            item.calibrated_status = state.get("calibrations", {}).get(
                item.knowledge_point_id
            )
        return DiagnosisResult(
            diagnosis_id=state["diagnosis_id"],
            user_id=state["user_id"],
            book_id=state["book_id"],
            learning_goal=state["learning_goal"],
            results=results,
            answer_records=state["answer_records"],
        )

