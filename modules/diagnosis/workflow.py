"""诊断流程编排。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from modules.common import api as common_api
from modules.common.errors import ResourceNotFoundError, ValidationAppError
from modules.learning_record.module import LearningRecordModule
from .repository import MySqlDiagnosisRepository

from .agent import DiagnosticAgent
from .field_rules import parse_answer_fields, parse_review_fields, parse_start_fields
from .models import (
    AnswerResult,
    DiagnosisResult,
    DiagnosisState,
    KnowledgePointResult,
    QuestionPlanningInput,
    STATUSES,
)
from .services import AssessmentService, DiagnosisResultStore, DiagnosisService


def build_diagnosis_graph(
    question_bank: Any,
    assessment_service: AssessmentService,
    checkpointer: Any,
    diagnostic_agent: DiagnosticAgent,
    knowledge_point_catalog: Any | None = None,
):
    """构建一轮诊断的固定状态机。"""

    def load_questions(state: DiagnosisState) -> dict[str, Any]:
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
        plan = diagnostic_agent.plan_questions(
            QuestionPlanningInput(
                learning_goal=state.get("learning_goal", ""),
                knowledge_point_mastery=state.get("knowledge_point_mastery", {}),
                knowledge_point_review=state.get("knowledge_point_review", {}),
                available_question_counts=question_bank.get_question_inventory(state["book_id"]),
                knowledge_point_catalog=catalog,
            )
        )
        plan_by_point = {
            item.knowledge_point_id: {
                "knowledge_point_id": item.knowledge_point_id,
                "question_count": item.question_count,
                "task_mode": item.task_mode,
            }
            for item in plan
        }
        questions, correct_answers = question_bank.get_questions(
            state["book_id"],
            question_plan=plan_by_point,
        )
        return {
            "questions": [DiagnosisService.question_payload(question) for question in questions],
            "correct_answers": correct_answers,
            "answers": {},
            "answer_metadata": {},
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
        answer_result = assessment_service.answer_result(
            DiagnosisService.questions_from_state(state["questions"]),
            state["answers"],
            state["correct_answers"],
            state.get("answer_metadata", {}),
        )
        current_states = state.get("knowledge_point_states", {})
        results = assessment_service.diagnose(answer_result, current_states=current_states)
        return {
            "draft_results": [common_api.serialization.to_data(item) for item in results],
            "answer_result": common_api.serialization.to_data(answer_result),
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
                raise ValidationAppError(
                    "calibration contains unknown knowledge points",
                    details={"ids": sorted(unknown)},
                )
            invalid = {key: value for key, value in calibrations.items() if value not in STATUSES[1:]}
            if invalid:
                raise ValidationAppError(
                    "calibration contains invalid statuses",
                    details={"values": invalid},
                )
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
    """诊断生命周期入口，过程状态只保存在 LangGraph。"""

    def __init__(
        self,
        question_bank: Any,
        result_store: DiagnosisResultStore,
        assessment_service: AssessmentService,
        diagnostic_agent: DiagnosticAgent,
        learning_record: LearningRecordModule | None = None,
        checkpointer: Any | None = None,
        knowledge_point_catalog: Any | None = None,
        database_repository: MySqlDiagnosisRepository | None = None,
        learning_plan: Any | None = None,
    ) -> None:
        self.result_store = result_store
        self.learning_record = learning_record
        self.database_repository = database_repository
        self.learning_plan = learning_plan
        self.graph = build_diagnosis_graph(
            question_bank,
            assessment_service,
            checkpointer or InMemorySaver(),
            diagnostic_agent,
            knowledge_point_catalog=knowledge_point_catalog,
        )

    @staticmethod
    def _config(diagnosis_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": diagnosis_id}}

    def _state(self, diagnosis_id: str) -> DiagnosisState:
        state = self.graph.get_state(self._config(diagnosis_id)).values
        if not state:
            raise ResourceNotFoundError(
                f"diagnosis not found: {diagnosis_id}",
                details={"resource": "diagnosis", "diagnosis_id": diagnosis_id},
            )
        return state

    def start_diagnosis(self, *, user_id: str, book_id: str, learning_goal: str, learning_plan_day_id: int | None = None, learning_plan_item_id: int | None = None) -> dict[str, Any]:
        values = parse_start_fields(user_id, book_id, learning_goal)
        diagnosis_id = f"diag_{uuid4().hex[:10]}"
        self.start(
            diagnosis_id=diagnosis_id,
            user_id=values["user_id"],
            book_id=values["book_id"],
            learning_goal=values["learning_goal"], learning_plan_day_id=learning_plan_day_id, learning_plan_item_id=learning_plan_item_id,
        )
        return {"diagnostic_id": diagnosis_id, "questions": self._state(diagnosis_id)["questions"]}

    def start(self, *, diagnosis_id: str, user_id: str, book_id: str, learning_goal: str, learning_plan_day_id: int | None = None, learning_plan_item_id: int | None = None) -> dict[str, Any]:
        knowledge_point_states = self._knowledge_point_states(user_id, book_id)
        mastery = {
            point_id: self._mastery_level(float(item.get("masteryScore") or 0.0))
            for point_id, item in knowledge_point_states.items()
        }
        review_by_point = {
            point_id: {"next_review_at": item.get("nextReviewAt")}
            for point_id, item in knowledge_point_states.items()
        }
        self.graph.invoke(
            {
                "diagnosis_id": diagnosis_id,
                "user_id": user_id,
                "book_id": book_id,
                "learning_goal": learning_goal,
                "knowledge_point_mastery": mastery,
                "knowledge_point_review": review_by_point,
                "knowledge_point_states": knowledge_point_states,
                "status": "started",
            },
            config=self._config(diagnosis_id),
        )
        if learning_plan_day_id is not None:
            if self.database_repository is None:
                raise RuntimeError("MySQL diagnosis repository is not configured")
            try:
                binding = self.database_repository.start_daily_session(user_id=int(user_id), learning_plan_day_id=learning_plan_day_id, learning_plan_item_id=learning_plan_item_id)
            except ValueError as exc:
                raise ValidationAppError("daily diagnosis requires a numeric userId") from exc
            self.graph.update_state(self._config(diagnosis_id), {"database_session_id": binding["session_id"], "database_plan_id": binding["plan_id"], "database_plan_item_id": binding.get("item_id")})
        return {"type": "answer_request", "diagnosis_id": diagnosis_id, "questions": self._state(diagnosis_id)["questions"]}

    def submit_answer(
        self,
        diagnosis_id: str,
        question_id: str,
        answer: str,
        skipped: bool = False,
    ) -> dict[str, Any]:
        values = parse_answer_fields(diagnosis_id, question_id, answer)
        state = self._state(values["diagnosis_id"])
        question = next(
            (item for item in state["questions"] if item["id"] == values["question_id"]),
            None,
        )
        if question is None:
            raise ResourceNotFoundError(
                "unknown question",
                details={"question_id": values["question_id"]},
            )
        if not skipped and values["answer"] not in {option["id"] for option in question["options"]}:
            raise ValidationAppError(
                "invalid answer",
                details={"question_id": values["question_id"]},
            )
        answers = dict(state.get("answers", {}))
        metadata = dict(state.get("answer_metadata", {}))
        previous = metadata.get(values["question_id"], {})
        answers[values["question_id"]] = "" if skipped else values["answer"]
        metadata[values["question_id"]] = {
            "hint_count": int(previous.get("hint_count", 0)),
            "retry_count": int(previous.get("retry_count", -1)) + 1,
            "is_independent": int(previous.get("hint_count", 0)) == 0,
            "is_delayed_retrieval": question.get("task_mode") == "retrieval",
            "occurred_at": datetime.now().astimezone().isoformat(),
        }
        self.graph.update_state(
            self._config(diagnosis_id),
            {"answers": answers, "answer_metadata": metadata},
        )
        return {"diagnostic_id": diagnosis_id, "question_id": question_id, "saved": True}

    async def finish_diagnosis(self, diagnosis_id: str) -> dict[str, Any]:
        state = self._state(diagnosis_id)
        await self.submit_async(diagnosis_id, state.get("answers", {}))
        state = self._state(diagnosis_id)
        answer_result = common_api.serialization.from_data(AnswerResult, state["answer_result"])
        results = [KnowledgePointResult(**item) for item in state.get("draft_results", [])]
        return DiagnosisService.summary(state["learning_goal"], answer_result, results)

    def confirm_diagnosis(
        self,
        diagnosis_id: str,
        *,
        calibration: str = "same",
        reason: str = "",
    ) -> DiagnosisResult | None:
        values = parse_review_fields(diagnosis_id, calibration, reason)
        state = self._state(diagnosis_id)
        calibrations = DiagnosisService.calibrations(state.get("draft_results", []), calibration)
        diagnosis = self.review(
            diagnosis_id,
            action="edit" if calibrations else "approve",
            calibrations=calibrations,
            calibration=values["calibration"],
            calibration_reason=values["reason"],
        )
        if diagnosis is not None:
            database_session_id = state.get("database_session_id")
            if database_session_id is not None:
                if self.database_repository is None or self.learning_plan is None:
                    raise RuntimeError("daily diagnosis persistence is not configured")
                self.database_repository.save_answers(session_id=int(database_session_id), records=diagnosis.answer_records)
                item_id = state.get("database_plan_item_id")
                if item_id is not None:
                    self.database_repository.complete_weekly_plan_item(user_id=int(state["user_id"]), item_id=int(item_id))
                else:
                    self.database_repository.complete_daily_diagnostic_task(session_id=int(database_session_id))
                self.learning_plan.replan_after_diagnostic(
                    plan_id=int(state["database_plan_id"]),
                    diagnostic_session_id=int(database_session_id),
                    rule_results=[common_api.serialization.to_data(item) for item in diagnosis.results],
                )
            if self.learning_record:
                self.learning_record.record_completed_diagnosis(diagnosis)
        return diagnosis

    def _knowledge_point_states(self, user_id: str, book_id: str) -> dict[str, dict[str, Any]]:
        if self.database_repository is None:
            return {}
        try:
            return self.database_repository.load_knowledge_point_states(
                user_id=int(user_id), book_id=self._database_book_id(book_id)
            )
        except ValueError:
            return {}

    @staticmethod
    def _database_book_id(book_id: str) -> int:
        """Map question-bank aliases to the corresponding MySQL book IDs."""

        aliases = {"ml": 2, "ml-001": 2, "machine_learning": 2, "dl": 1, "dl-001": 1, "deep_learning": 1}
        return aliases[str(book_id)] if str(book_id) in aliases else int(book_id)

    @staticmethod
    def _mastery_level(score: float) -> str:
        if score >= 0.75:
            return "掌握"
        if score >= 0.50:
            return "熟悉"
        if score >= 0.25:
            return "了解"
        return "不会"

    async def submit_async(self, diagnosis_id: str, answers: dict[str, str]) -> dict[str, Any]:
        result = await self.graph.ainvoke(
            Command(resume=answers),
            config=self._config(diagnosis_id),
        )
        return result["__interrupt__"][0].value

    def submit(self, diagnosis_id: str, answers: dict[str, str]) -> dict[str, Any]:
        result = self.graph.invoke(
            Command(resume=answers),
            config=self._config(diagnosis_id),
        )
        return result["__interrupt__"][0].value

    def review(
        self,
        diagnosis_id: str,
        *,
        action: str = "approve",
        calibrations: dict[str, str] | None = None,
        calibration: str = "same",
        calibration_reason: str = "",
    ) -> DiagnosisResult | None:
        result = self.graph.invoke(
            Command(resume={"action": action, "calibrations": calibrations or {}}),
            config=self._config(diagnosis_id),
        )
        if result["status"] == "rejected":
            return None
        state = self._state(diagnosis_id)
        diagnosis = DiagnosisService.final_result(
            diagnosis_id=diagnosis_id,
            user_id=state["user_id"],
            book_id=state["book_id"],
            learning_goal=state["learning_goal"],
            draft_results=state["draft_results"],
            answer_result=state["answer_result"],
            calibration=calibration,
            calibration_reason=calibration_reason,
        )
        self.result_store.save(diagnosis)
        return diagnosis
