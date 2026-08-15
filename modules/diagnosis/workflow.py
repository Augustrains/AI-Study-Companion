"""LangGraph orchestration for the diagnosis module."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from modules.common.errors import ResourceNotFoundError, ValidationAppError
from modules.learning_record.module import LearningRecordModule
from modules.memory.module import MemoryModule

from .agent import DiagnosticAgent, DiagnosticAnalysisInput, QuestionPlanningInput
from .field_rules import parse_answer_fields, parse_review_fields, parse_start_fields
from .models import DiagnosisState, DiagnosticSession, DiagnosisResult, STATUSES
from .services import AssessmentService, DiagnosisService, DiagnosticSessionStore
from .services import QuestionBank

# Kept as compatibility exports for existing bootstrap/tests.
__all__ = [
    "AssessmentService",
    "DiagnosticSessionStore",
    "DiagnosisState",
    "DiagnosisWorkflow",
    "build_diagnosis_graph",
]




def build_diagnosis_graph(
    question_bank: QuestionBank,
    assessment_service: AssessmentService,
    checkpointer: Any,
    diagnostic_agent: DiagnosticAgent,
    memory: MemoryModule | None = None,
    knowledge_point_catalog: Any | None = None,
):
    """Build the fixed diagnosis state machine.

    Nodes only translate graph state and delegate business work to services.
    """

    def load_questions(state: DiagnosisState) -> dict[str, Any]:
        available_question_counts = question_bank.get_question_inventory(state["book_id"])
        domain = {
            "ml": "machine_learning",
            "ml-001": "machine_learning",
            "machine_learning": "machine_learning",
            "dl": "deep_learning",
            "dl-001": "deep_learning",
            "deep_learning": "deep_learning",
        }.get(state["book_id"], state["book_id"])
        catalog = {
            item["id"]: item
            for item in (knowledge_point_catalog.as_dicts(domain) if knowledge_point_catalog else [])
        }
        question_plan = diagnostic_agent.plan_questions(
            QuestionPlanningInput(
                learning_goal=state.get("learning_goal", ""),
                knowledge_point_mastery=state.get("knowledge_point_mastery", {}),
                knowledge_point_memory=state.get("knowledge_point_memory", {}),
                available_question_counts=available_question_counts,
                knowledge_point_catalog=catalog,
            )
        )
        serialized_plan = [
            {
                "knowledge_point_id": item.knowledge_point_id,
                "question_count": item.question_count,
                "task_mode": item.task_mode,
            }
            for item in question_plan
        ]
        question_set = question_bank.get_questions(
            state["book_id"],
            state.get("learning_goal", ""),
            knowledge_point_mastery=state.get("knowledge_point_mastery", {}),
            task_context=state.get("task_context", {}),
            question_plan={item["knowledge_point_id"]: item for item in serialized_plan},
        )
        return {
            "questions": [DiagnosisService.question_payload(q) for q in question_set.questions],
            "correct_answers": question_set.correct_answers,
            "question_plan": serialized_plan,
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
            raise ValueError("answers must be a question ID to answer mapping")
        return {"answers": answers, "status": "evaluating"}

    def evaluate_answers(state: DiagnosisState) -> dict[str, Any]:
        results, records = assessment_service.evaluate(
            DiagnosisService.questions_from_state(state["questions"]),
            state["answers"],
            state["correct_answers"],
            current_states=(
                {
                    item.knowledge_point_id: {
                        "masteryScore": item.mastery_score,
                        "evidenceSummary": item.evidence_summary.to_rule_payload(),
                    }
                    for item in memory.get_learner_memory(state["user_id"], state["book_id"]).knowledge_points
                }
                if memory
                else {}
            ),
        )
        total = len(records)
        answered = sum(not item.get("skipped", False) for item in records)
        correct = sum(bool(item.get("is_correct")) for item in records)
        statuses = [item.ai_status for item in results if item.ai_status in STATUSES]
        analysis_input = DiagnosticAnalysisInput(
            diagnosis_id=state["diagnosis_id"],
            learning_goal=state.get("learning_goal", ""),
            total_questions=total,
            answered_questions=answered,
            skipped_questions=total - answered,
            correct_questions=correct,
            accuracy=float(round(correct / total * 100, 2)) if total else 0.0,
            level=max(statuses, key=STATUSES.index) if statuses else STATUSES[0],
            confidence="high" if answered >= total else "medium",
            knowledge_point_results=[result.__dict__.copy() for result in results],
            question_results=records,
        )
        return {
            "draft_results": analysis_input.knowledge_point_results,
            "answer_records": records,
            "analysis_input": analysis_input.__dict__.copy(),
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
            raise ValueError("review decision must be an object")
        action = decision.get("action")
        if action not in {"approve", "edit", "reject"}:
            raise ValueError(f"unsupported review action: {action}")
        calibrations = decision.get("calibrations", {})
        if not isinstance(calibrations, dict):
            raise ValueError("calibrations must be an object")
        if action == "edit":
            known = {item["knowledge_point_id"] for item in state["draft_results"]}
            unknown = set(calibrations) - known
            if unknown:
                raise ValidationAppError("calibration contains unknown knowledge points", details={"ids": sorted(unknown)})
            invalid = {key: value for key, value in calibrations.items() if value not in STATUSES[1:]}
            if invalid:
                raise ValidationAppError("calibration contains invalid statuses", details={"values": invalid})
        return {
            "review_action": action,
            "calibrations": calibrations if action == "edit" else {},
            "status": "rejected" if action == "reject" else "approved",
        }

    builder = StateGraph(DiagnosisState)
    builder.add_node("load_questions", load_questions)
    builder.add_node("wait_for_answers", wait_for_answers)
    builder.add_node("evaluate_answers", evaluate_answers)
    builder.add_node("wait_for_review", wait_for_review)
    builder.add_node("commit", lambda _: {"status": "completed"})
    builder.add_node("finish_rejected", lambda _: {"status": "rejected"})
    builder.add_edge(START, "load_questions")
    builder.add_edge("load_questions", "wait_for_answers")
    builder.add_edge("wait_for_answers", "evaluate_answers")
    builder.add_edge("evaluate_answers", "wait_for_review")
    builder.add_conditional_edges(
        "wait_for_review",
        lambda state: "finish_rejected" if state["review_action"] == "reject" else "commit",
        {"commit": "commit", "finish_rejected": "finish_rejected"},
    )
    builder.add_edge("commit", END)
    builder.add_edge("finish_rejected", END)
    return builder.compile(checkpointer=checkpointer)


class DiagnosisWorkflow:
    """Public lifecycle API around the diagnosis LangGraph."""

    def __init__(
        self,
        question_bank: QuestionBank,
        session_store: DiagnosticSessionStore,
        assessment_service: AssessmentService,
        diagnostic_agent: DiagnosticAgent,
        memory: MemoryModule | None = None,
        learning_record: LearningRecordModule | None = None,
        checkpointer: Any | None = None,
        knowledge_point_catalog: Any | None = None,
    ) -> None:
        self.session_store = session_store
        self.memory = memory
        self.learning_record = learning_record
        self.diagnostic_agent = diagnostic_agent
        self.graph = build_diagnosis_graph(
            question_bank,
            assessment_service,
            checkpointer or InMemorySaver(),
            diagnostic_agent,
            memory=memory,
            knowledge_point_catalog=knowledge_point_catalog,
        )

    @staticmethod
    def _config(diagnosis_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": diagnosis_id}}

    def start_diagnosis(self, *, user_id: str, book_id: str, learning_goal: str) -> dict[str, Any]:
        values = parse_start_fields(user_id, book_id, learning_goal)
        session = DiagnosticSession(
            id=f"diag_{uuid4().hex[:10]}",
            user_id=values["user_id"],
            book_id=values["book_id"],
            learning_goal=values["learning_goal"],
        )
        self.start(session)
        return {"diagnostic_id": session.id, "questions": session.questions}

    def submit_answer(self, diagnosis_id: str, question_id: str, answer: str, skipped: bool = False) -> dict[str, Any]:
        values = parse_answer_fields(diagnosis_id, question_id, answer)
        session = self.session_store.get(values["diagnosis_id"])
        question = next((item for item in session.questions if item["id"] == values["question_id"]), None)
        if question is None:
            raise ResourceNotFoundError("unknown question", details={"question_id": values["question_id"]})
        if not skipped and values["answer"] not in {option["id"] for option in question["options"]}:
            raise ValidationAppError("invalid answer", details={"question_id": values["question_id"]})
        previous_metadata = session.answer_metadata.get(values["question_id"], {})
        session.answers[values["question_id"]] = "" if skipped else values["answer"]
        session.answer_metadata[values["question_id"]] = {
            "hint_count": int(previous_metadata.get("hint_count", 0)),
            "retry_count": int(previous_metadata.get("retry_count", -1)) + 1,
            "is_independent": int(previous_metadata.get("hint_count", 0)) == 0,
            "is_delayed_retrieval": False,
            "occurred_at": datetime.now().astimezone().isoformat(),
        }
        self.session_store.save(session)
        return {"diagnostic_id": diagnosis_id, "question_id": question_id, "saved": True}

    async def finish_diagnosis(self, diagnosis_id: str) -> dict[str, Any]:
        session = self.session_store.get(diagnosis_id)
        await self.submit_async(diagnosis_id, session.answers)
        records = DiagnosisService.question_records(session)
        total = len(records)
        answered = sum(not item["skipped"] for item in records)
        correct = sum(bool(item["is_correct"]) for item in records)
        state = self.graph.get_state(self._config(diagnosis_id)).values
        results = state.get("draft_results", [])
        analysis = await self.diagnostic_agent.analyze_performance(
            DiagnosticAnalysisInput(**state["analysis_input"])
        )
        session.status = "awaiting_review"
        self.session_store.save(session)
        return DiagnosisService.summary(session, results, analysis)

    def confirm_diagnosis(self, diagnosis_id: str, *, calibration: str = "same", reason: str = "") -> DiagnosisResult | None:
        values = parse_review_fields(diagnosis_id, calibration, reason)
        state = self.graph.get_state(self._config(values["diagnosis_id"])).values
        calibrations = self._calibrations(state.get("draft_results", []), values["calibration"])
        diagnosis = self.review(values["diagnosis_id"], action="edit" if calibrations else "approve", calibrations=calibrations)
        if diagnosis is None:
            return None
        session = self.session_store.get(values["diagnosis_id"])
        session.calibration = values["calibration"]
        session.calibration_reason = values["reason"]
        if session.result is not None:
            session.result["calibration"] = {
                "adjustment": values["calibration"],
                "reason": values["reason"],
            }
        self.session_store.save(session)
        if self.learning_record:
            self.learning_record.record_completed_diagnosis(diagnosis)
        if self.memory:
            self.memory.ingest_diagnosis(diagnosis)
        return diagnosis

    @staticmethod
    def _calibrations(results: list[dict[str, Any]], calibration: str) -> dict[str, str]:
        if calibration == "same":
            return {}
        delta = -1 if calibration == "lower" else 1
        statuses = STATUSES[1:]
        return {
            item["knowledge_point_id"]: statuses[max(0, min(len(statuses) - 1, statuses.index(item["ai_status"]) + delta))]
            for item in results
        }


    def start(self, session: DiagnosticSession) -> dict[str, Any]:
        learner_memory = self.memory.get_learner_memory(session.user_id, session.book_id) if self.memory else None
        knowledge_point_mastery = (
            {item.knowledge_point_id: item.mastery_level for item in learner_memory.knowledge_points}
            if learner_memory
            else {}
        )
        knowledge_point_memory = (
            {
                item.knowledge_point_id: {
                    "mastery_level": item.mastery_level,
                    "mastery_score": item.mastery_score,
                    "confidence": item.confidence,
                    "memory_status": item.memory_status,
                    "memory_stability_days": item.memory_stability_days,
                    "next_review_at": item.next_review_at,
                }
                for item in learner_memory.knowledge_points
            }
            if learner_memory
            else {}
        )
        self.session_store.save(session)
        self.graph.invoke(
            {
                "workflow_run_id": session.id,
                "diagnosis_id": session.id,
                "diagnostic_session_id": session.id,
                "user_id": session.user_id,
                "book_id": session.book_id,
                "learning_goal": session.learning_goal,
                "knowledge_point_mastery": knowledge_point_mastery,
                "knowledge_point_memory": knowledge_point_memory,
                "status": "started",
            },
            config=self._config(session.id),
        )
        state = self.graph.get_state(self._config(session.id)).values
        session.questions = state.get("questions", [])
        session.correct_answers = state.get("correct_answers", {})
        self.session_store.save(session)
        return {"type": "answer_request", "diagnosis_id": session.id, "questions": session.questions}

    async def submit_async(self, diagnosis_id: str, answers: dict[str, str]) -> dict[str, Any]:
        session = self.session_store.get(diagnosis_id)
        session.answers = dict(answers)
        result = await self.graph.ainvoke(Command(resume=answers), config=self._config(diagnosis_id))
        session.status = "awaiting_review"
        self.session_store.save(session)
        return result["__interrupt__"][0].value

    def submit(self, diagnosis_id: str, answers: dict[str, str]) -> dict[str, Any]:
        session = self.session_store.get(diagnosis_id)
        session.answers = dict(answers)
        result = self.graph.invoke(Command(resume=answers), config=self._config(diagnosis_id))
        session.status = "awaiting_review"
        self.session_store.save(session)
        return result["__interrupt__"][0].value

    def review(self, diagnosis_id: str, *, action: str = "approve", calibrations: dict[str, str] | None = None) -> DiagnosisResult | None:
        result = self.graph.invoke(
            Command(resume={"action": action, "calibrations": calibrations or {}}),
            config=self._config(diagnosis_id),
        )
        session = self.session_store.get(diagnosis_id)
        if result["status"] == "rejected":
            session.status = "rejected"
            self.session_store.save(session)
            return None
        state = self.graph.get_state(self._config(diagnosis_id)).values
        diagnosis = DiagnosisService.final_result(session, state["draft_results"], state.get("calibrations", {}))
        session.status = "completed"
        session.result = {
            "results": [item.__dict__.copy() for item in diagnosis.results],
            "answer_records": diagnosis.answer_records,
        }
        self.session_store.save(session)
        return diagnosis
