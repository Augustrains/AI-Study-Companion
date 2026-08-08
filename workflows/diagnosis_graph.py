from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from agents.diagnostic_agent import DiagnosticAgent
from domain.assessment_service import AssessmentService
from domain.models import DiagnosisResult, KnowledgePointResult, STATUSES
from repositories.question_repository import QuestionRepository
from repositories.session_repository import InMemoryLearningSessionRepository
from workflows.diagnosis_state import DiagnosisState


def build_diagnosis_graph(
    *,
    question_repository: QuestionRepository,
    session_repository: InMemoryLearningSessionRepository,
    assessment_service: AssessmentService,
    diagnostic_agent: DiagnosticAgent,
    checkpointer: Any,
):
    """构建并编译诊断图；一份图定义服务多个 thread。"""

    def load_questions(state: DiagnosisState) -> dict[str, Any]:
        questions = question_repository.get_diagnosis_questions(
            state["book_id"], state["learning_goal"]
        )
        return {
            "questions": [
                {
                    "id": question.id,
                    "knowledge_point_id": question.knowledge_point_id,
                    "question": question.question,
                    "options": question.options,
                }
                for question in questions
            ],
            "status": "waiting_for_answers",
        }

    def wait_for_answers(state: DiagnosisState) -> dict[str, Any]:
        answers = interrupt(
            {
                "type": "answer_request",
                "diagnosis_id": state["diagnosis_id"],
                "questions": state["questions"],
            }
        )
        if not isinstance(answers, dict):
            raise ValueError("提交答案必须是题目 ID 到答案的字典")
        return {"answers": answers, "status": "evaluating"}

    def evaluate_answers(state: DiagnosisState) -> dict[str, Any]:
        questions = question_repository.get_diagnosis_questions(
            state["book_id"], state["learning_goal"]
        )
        results, answer_records = assessment_service.evaluate(
            questions, state["answers"]
        )
        return {
            "draft_results": [result.__dict__.copy() for result in results],
            "answer_records": answer_records,
        }

    def explain_results(state: DiagnosisState) -> dict[str, Any]:
        explained_results: list[dict[str, Any]] = []
        for item in state["draft_results"]:
            result = KnowledgePointResult(**item)
            result.explanation = diagnostic_agent.explain(result)
            explained_results.append(result.__dict__.copy())
        return {
            "draft_results": explained_results,
            "status": "waiting_for_review",
        }

    def wait_for_review(state: DiagnosisState) -> dict[str, Any]:
        decision = interrupt(
            {
                "type": "diagnosis_review",
                "diagnosis_id": state["diagnosis_id"],
                "draft_results": state["draft_results"],
                "allowed_actions": ["approve", "edit", "reject"],
            }
        )
        if not isinstance(decision, dict):
            raise ValueError("确认结果必须是包含 action 的字典")

        action = decision.get("action")
        if action not in {"approve", "edit", "reject"}:
            raise ValueError(f"不支持的确认操作: {action}")

        calibrations = decision.get("calibrations", {})
        if not isinstance(calibrations, dict):
            raise ValueError("calibrations 必须是知识点到状态的字典")
        if action == "edit":
            known_points = {
                item["knowledge_point_id"] for item in state["draft_results"]
            }
            unknown_points = set(calibrations) - known_points
            if unknown_points:
                raise ValueError(f"校准包含未知知识点: {sorted(unknown_points)}")
            invalid = {
                knowledge_point_id: status
                for knowledge_point_id, status in calibrations.items()
                if status not in STATUSES[1:]
            }
            if invalid:
                raise ValueError(f"包含不支持的校准状态: {invalid}")

        return {
            "review_action": action,
            "calibrations": calibrations if action == "edit" else {},
            "status": "rejected" if action == "reject" else "approved",
        }

    def route_after_review(state: DiagnosisState) -> str:
        return "finish_rejected" if state["review_action"] == "reject" else "commit"

    def commit_diagnosis(state: DiagnosisState) -> dict[str, Any]:
        session = session_repository.get(state["learning_session_id"])

        # interrupt 恢复时节点可能重放；diagnosis_id 作为幂等键避免重复写历史。
        already_committed = any(
            item["diagnosis_id"] == state["diagnosis_id"]
            for item in session.diagnosis_history
        )
        if not already_committed:
            results = [
                KnowledgePointResult(**item) for item in state["draft_results"]
            ]
            for result in results:
                if result.knowledge_point_id in state.get("calibrations", {}):
                    result.calibrated_status = state["calibrations"][
                        result.knowledge_point_id
                    ]

            diagnosis = DiagnosisResult(
                diagnosis_id=state["diagnosis_id"],
                user_id=state["user_id"],
                book_id=state["book_id"],
                learning_goal=state["learning_goal"],
                results=results,
                answer_records=state["answer_records"],
            )
            session.apply_diagnosis(diagnosis)
            for knowledge_point_id, status in state.get("calibrations", {}).items():
                session.calibrate(knowledge_point_id, status)
            session_repository.save(session)

        return {"status": "completed"}

    def finish_rejected(_: DiagnosisState) -> dict[str, Any]:
        return {"status": "rejected"}

    builder = StateGraph(DiagnosisState)
    builder.add_node("load_questions", load_questions)
    builder.add_node("wait_for_answers", wait_for_answers)
    builder.add_node("evaluate_answers", evaluate_answers)
    builder.add_node("explain_results", explain_results)
    builder.add_node("wait_for_review", wait_for_review)
    builder.add_node("commit", commit_diagnosis)
    builder.add_node("finish_rejected", finish_rejected)

    builder.add_edge(START, "load_questions")
    builder.add_edge("load_questions", "wait_for_answers")
    builder.add_edge("wait_for_answers", "evaluate_answers")
    builder.add_edge("evaluate_answers", "explain_results")
    builder.add_edge("explain_results", "wait_for_review")
    builder.add_conditional_edges(
        "wait_for_review",
        route_after_review,
        {"commit": "commit", "finish_rejected": "finish_rejected"},
    )
    builder.add_edge("commit", END)
    builder.add_edge("finish_rejected", END)
    return builder.compile(checkpointer=checkpointer)
