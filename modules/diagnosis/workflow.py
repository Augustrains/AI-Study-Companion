"""诊断流程编排。"""

from __future__ import annotations

from datetime import datetime
from threading import RLock
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from modules.common import api as common_api
from modules.common.errors import (
    ResourceNotFoundError,
    ValidationAppError,
    WorkflowStateError,
)
from modules.context.builder import ContextBuilder
from modules.learning_record.module import LearningRecordModule
from modules.memory.module import MemoryModule
from modules.persistence.workflows import WorkflowSessionRepository

from .agent import DiagnosticAgent
from .field_rules import parse_answer_fields, parse_review_fields, parse_start_fields
from .models import (
    STATUSES,
    AnswerResult,
    DiagnosisResult,
    DiagnosisState,
    KnowledgePointResult,
    QuestionPlanningInput,
)
from .services import AssessmentService, DiagnosisResultStore, DiagnosisService


def build_diagnosis_graph(
    question_bank: Any,
    assessment_service: AssessmentService,
    checkpointer: Any,
    diagnostic_agent: DiagnosticAgent,
    memory: MemoryModule | None = None,
    knowledge_point_catalog: Any | None = None,
    context_builder: ContextBuilder | None = None,
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
            for item in (
                knowledge_point_catalog.as_dicts(domain)
                if knowledge_point_catalog
                else []
            )
        }
        inventory = question_bank.get_question_inventory(state["book_id"])
        context = None
        mastery = state.get("knowledge_point_mastery", {})
        memory_by_point = state.get("knowledge_point_memory", {})
        if context_builder is not None:
            context = context_builder.for_diagnosis(
                request_id=f"diagnosis:{state['diagnosis_id']}:question-plan",
                user_id=state["user_id"],
                book_id=state["book_id"],
                current_input=state.get("learning_goal", ""),
                learning_goal=state.get("learning_goal", ""),
                workflow_state={
                    "knowledgePoints": [
                        {
                            **catalog.get(
                                point_id,
                                {"id": point_id, "name": "", "description": ""},
                            ),
                            "availableQuestionCount": inventory.get(point_id, 0),
                        }
                        for point_id in inventory
                    ],
                },
                knowledge_point_ids=list(inventory),
            )
            mastery = {
                item.knowledge_point_id: item.assessed_mastery_level
                for item in context.learner.verified_mastery
            }
            memory_by_point = {
                item.knowledge_point_id: {
                    "mastery_level": item.assessed_mastery_level,
                    "mastery_score": item.mastery_score,
                    "confidence": item.confidence,
                    "memory_status": item.memory_status,
                    "memory_stability_days": item.memory_stability_days,
                    "next_review_at": item.next_review_at,
                    "evidence_ids": item.evidence_ids,
                    "reason_codes": item.reason_codes,
                    "algorithm_name": item.algorithm_name,
                    "algorithm_version": item.algorithm_version,
                }
                for item in context.learner.verified_mastery
            }
        plan = diagnostic_agent.plan_questions(
            QuestionPlanningInput(
                learning_goal=state.get("learning_goal", ""),
                knowledge_point_mastery=mastery,
                knowledge_point_memory=memory_by_point,
                available_question_counts=inventory,
                knowledge_point_catalog=catalog,
                context=context,
            )
        )
        if context is not None:
            context_builder.record_trace(context)
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
        result = {
            "questions": [
                DiagnosisService.question_payload(question) for question in questions
            ],
            "correct_answers": correct_answers,
            "answers": {},
            "answer_metadata": {},
            "status": "waiting_for_answers",
        }
        if context is not None:
            result["context_id"] = context.identity.context_id
            result["knowledge_point_mastery"] = mastery
            result["knowledge_point_memory"] = memory_by_point
        return result

    def wait_for_answers(state: DiagnosisState) -> dict[str, Any]:
        answers = interrupt(
            {
                "type": "answer_request",
                "diagnosis_id": state["diagnosis_id"],
                "questions": state["questions"],
            }
        )
        if not isinstance(answers, dict):
            raise TypeError("answers must be a question ID to answer mapping")
        return {"answers": answers, "status": "evaluating"}

    def evaluate_answers(state: DiagnosisState) -> dict[str, Any]:
        answer_result = assessment_service.answer_result(
            DiagnosisService.questions_from_state(state["questions"]),
            state["answers"],
            state["correct_answers"],
            state.get("answer_metadata", {}),
        )
        current_states = {}
        if memory:
            current_states = {
                item.knowledge_point_id: {
                    "masteryScore": item.mastery_score,
                    "evidenceSummary": item.evidence_summary.to_rule_payload(),
                }
                for item in memory.get_learner_memory(
                    state["user_id"], state["book_id"]
                ).knowledge_points
            }
        results = assessment_service.diagnose(
            answer_result, current_states=current_states
        )
        return {
            "draft_results": [
                common_api.serialization.to_data(item) for item in results
            ],
            "answer_result": common_api.serialization.to_data(answer_result),
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
            raise TypeError("review decision must be an object")
        action = decision.get("action")
        if action not in {"approve", "edit", "reject"}:
            raise ValueError(f"unsupported review action: {action}")
        calibrations = decision.get("calibrations", {})
        if not isinstance(calibrations, dict):
            raise TypeError("calibrations must be an object")
        if action == "edit":
            known = {item["knowledge_point_id"] for item in state["draft_results"]}
            unknown = set(calibrations) - known
            if unknown:
                raise ValidationAppError(
                    "calibration contains unknown knowledge points",
                    details={"ids": sorted(unknown)},
                )
            invalid = {
                key: value
                for key, value in calibrations.items()
                if value not in STATUSES[1:]
            }
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
        lambda state: (
            "finish_rejected" if state["review_action"] == "reject" else "commit"
        ),
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
        memory: MemoryModule | None = None,
        learning_record: LearningRecordModule | None = None,
        checkpointer: Any | None = None,
        knowledge_point_catalog: Any | None = None,
        context_builder: ContextBuilder | None = None,
        workflow_sessions: WorkflowSessionRepository | None = None,
    ) -> None:
        self.result_store = result_store
        self.memory = memory
        self.learning_record = learning_record
        self.context_builder = context_builder
        self.workflow_sessions = workflow_sessions
        self._lock_registry_guard = RLock()
        self._diagnosis_locks: dict[str, RLock] = {}
        self.graph = build_diagnosis_graph(
            question_bank,
            assessment_service,
            checkpointer or InMemorySaver(),
            diagnostic_agent,
            memory=memory,
            knowledge_point_catalog=knowledge_point_catalog,
            context_builder=context_builder,
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

    def _state_for_user(
        self,
        diagnosis_id: str,
        actor_user_id: str | None,
    ) -> DiagnosisState:
        if self.workflow_sessions is not None:
            if not actor_user_id:
                raise ValidationAppError("actor_user_id is required")
            self.workflow_sessions.require_owned(
                diagnosis_id,
                actor_user_id=actor_user_id,
                workflow_type="diagnosis",
            )
        state = self._state(diagnosis_id)
        if actor_user_id and state.get("user_id") != actor_user_id:
            raise ResourceNotFoundError(
                "diagnosis not found",
                details={"resource": "diagnosis", "diagnosis_id": diagnosis_id},
            )
        return state

    def _lock_for(self, diagnosis_id: str) -> RLock:
        """Return the process-local re-entrant lock for one diagnosis run."""

        with self._lock_registry_guard:
            return self._diagnosis_locks.setdefault(diagnosis_id, RLock())

    @staticmethod
    def _require_status(
        state: DiagnosisState,
        *,
        allowed: set[str],
        operation: str,
    ) -> None:
        status = str(state.get("status", ""))
        if status not in allowed:
            raise WorkflowStateError(
                f"diagnosis cannot {operation} while status is {status or 'unknown'}",
                details={
                    "diagnosis_id": state.get("diagnosis_id", ""),
                    "status": status or "unknown",
                    "operation": operation,
                    "allowed_statuses": sorted(allowed),
                },
            )

    @staticmethod
    def _summary_from_state(state: DiagnosisState) -> dict[str, Any]:
        answer_payload = state.get("answer_result")
        if not isinstance(answer_payload, dict):
            raise WorkflowStateError(
                "diagnosis has no evaluated answer result",
                details={
                    "diagnosis_id": state.get("diagnosis_id", ""),
                    "status": state.get("status", "unknown"),
                },
            )
        answer_result = common_api.serialization.from_data(
            AnswerResult,
            answer_payload,
        )
        results = [
            KnowledgePointResult(**item) for item in state.get("draft_results", [])
        ]
        summary = DiagnosisService.summary(
            state.get("learning_goal", ""),
            answer_result,
            results,
        )
        # ``DiagnosisService.summary`` uses the current clock.  Reusing the
        # latest immutable answer timestamp makes retry responses stable across
        # process restarts without adding another checkpoint field.
        evidence_times = [
            record.occurred_at
            for record in answer_result.answer_records
            if record.occurred_at
        ]
        if evidence_times:
            summary["generated_at"] = max(evidence_times)
        return summary

    def _saved_result(
        self,
        diagnosis_id: str,
        actor_user_id: str | None,
    ) -> DiagnosisResult | None:
        try:
            if actor_user_id is not None:
                return self.result_store.get_owned(diagnosis_id, actor_user_id)
            return self.result_store.get(diagnosis_id)
        except ResourceNotFoundError:
            return None

    def start_diagnosis(
        self, *, user_id: str, book_id: str, learning_goal: str
    ) -> dict[str, Any]:
        values = parse_start_fields(user_id, book_id, learning_goal)
        diagnosis_id = f"diag_{uuid4().hex[:10]}"
        self.start(
            diagnosis_id=diagnosis_id,
            user_id=values["user_id"],
            book_id=values["book_id"],
            learning_goal=values["learning_goal"],
        )
        return {
            "diagnostic_id": diagnosis_id,
            "questions": self._state(diagnosis_id)["questions"],
        }

    def start(
        self, *, diagnosis_id: str, user_id: str, book_id: str, learning_goal: str
    ) -> dict[str, Any]:
        with self._lock_for(diagnosis_id):
            learner_memory = (
                self.memory.get_learner_memory(user_id, book_id)
                if self.memory and self.context_builder is None
                else None
            )
            mastery = (
                {
                    item.knowledge_point_id: item.mastery_level
                    for item in learner_memory.knowledge_points
                }
                if learner_memory
                else {}
            )
            memory_by_point = (
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
            if self.workflow_sessions is not None:
                self.workflow_sessions.create(
                    workflow_id=diagnosis_id,
                    user_id=user_id,
                    workflow_type="diagnosis",
                    learning_domain=book_id,
                )
            self.graph.invoke(
                {
                    "diagnosis_id": diagnosis_id,
                    "user_id": user_id,
                    "book_id": book_id,
                    "learning_goal": learning_goal,
                    "knowledge_point_mastery": mastery,
                    "knowledge_point_memory": memory_by_point,
                    "status": "started",
                },
                config=self._config(diagnosis_id),
            )
            return {
                "type": "answer_request",
                "diagnosis_id": diagnosis_id,
                "questions": self._state(diagnosis_id)["questions"],
            }

    def submit_answer(
        self,
        diagnosis_id: str,
        question_id: str,
        answer: str,
        skipped: bool = False,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        values = parse_answer_fields(diagnosis_id, question_id, answer)
        with self._lock_for(values["diagnosis_id"]):
            state = self._state_for_user(values["diagnosis_id"], actor_user_id)
            self._require_status(
                state,
                allowed={"waiting_for_answers"},
                operation="accept answers",
            )
            question = next(
                (
                    item
                    for item in state["questions"]
                    if item["id"] == values["question_id"]
                ),
                None,
            )
            if question is None:
                raise ResourceNotFoundError(
                    "unknown question",
                    details={"question_id": values["question_id"]},
                )
            if not skipped and values["answer"] not in {
                option["id"] for option in question["options"]
            }:
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
            return {
                "diagnostic_id": diagnosis_id,
                "question_id": question_id,
                "saved": True,
            }

    async def finish_diagnosis(
        self,
        diagnosis_id: str,
        *,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        # The application injects synchronous SqliteSaver/PostgresSaver
        # instances.  Keep this coroutine-compatible API for callers, but drive
        # the graph synchronously so persistent savers never receive aget/aput.
        with self._lock_for(diagnosis_id):
            state = self._state_for_user(diagnosis_id, actor_user_id)
            if isinstance(state.get("answer_result"), dict):
                if self.workflow_sessions is not None and state.get("status") in {
                    "waiting_for_review",
                    "evaluating",
                }:
                    self.workflow_sessions.update_status(
                        diagnosis_id,
                        "waiting_for_review",
                    )
                return self._summary_from_state(state)
            self._require_status(
                state,
                allowed={"waiting_for_answers"},
                operation="finish",
            )
            self.submit(
                diagnosis_id,
                state.get("answers", {}),
                actor_user_id=actor_user_id,
            )
            state = self._state_for_user(diagnosis_id, actor_user_id)
            if self.workflow_sessions is not None:
                self.workflow_sessions.update_status(
                    diagnosis_id,
                    "waiting_for_review",
                )
            return self._summary_from_state(state)

    def confirm_diagnosis(
        self,
        diagnosis_id: str,
        *,
        calibration: str = "same",
        reason: str = "",
        actor_user_id: str | None = None,
    ) -> DiagnosisResult | None:
        values = parse_review_fields(diagnosis_id, calibration, reason)
        with self._lock_for(diagnosis_id):
            state = self._state_for_user(diagnosis_id, actor_user_id)
            calibrations = DiagnosisService.calibrations(
                state.get("draft_results", []), calibration
            )
            diagnosis = self.review(
                diagnosis_id,
                action="edit" if calibrations else "approve",
                calibrations=calibrations,
                calibration=values["calibration"],
                calibration_reason=values["reason"],
                actor_user_id=actor_user_id,
            )
            if diagnosis is not None:
                if self.learning_record:
                    self.learning_record.record_completed_diagnosis(diagnosis)
                if self.memory:
                    self.memory.ingest_diagnosis(diagnosis)
            return diagnosis

    async def submit_async(
        self,
        diagnosis_id: str,
        answers: dict[str, str],
        *,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        return self.submit(
            diagnosis_id,
            answers,
            actor_user_id=actor_user_id,
        )

    def submit(
        self,
        diagnosis_id: str,
        answers: dict[str, str],
        *,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock_for(diagnosis_id):
            state = self._state_for_user(diagnosis_id, actor_user_id)
            self._require_status(
                state,
                allowed={"waiting_for_answers"},
                operation="submit answers",
            )
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
        actor_user_id: str | None = None,
    ) -> DiagnosisResult | None:
        with self._lock_for(diagnosis_id):
            state = self._state_for_user(diagnosis_id, actor_user_id)
            status = str(state.get("status", ""))
            if status == "rejected":
                if self.workflow_sessions is not None:
                    self.workflow_sessions.update_status(diagnosis_id, "rejected")
                return None
            if status == "completed":
                saved = self._saved_result(diagnosis_id, actor_user_id)
                if saved is not None:
                    if self.workflow_sessions is not None:
                        self.workflow_sessions.update_status(
                            diagnosis_id,
                            "completed",
                        )
                    return saved
            else:
                # ``evaluating`` is accepted for checkpoints created by the
                # previous graph version, which interrupted review before it
                # had an explicit waiting_for_review status.
                self._require_status(
                    state,
                    allowed={"waiting_for_review", "evaluating"},
                    operation="review",
                )
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
                    if self.workflow_sessions is not None:
                        self.workflow_sessions.update_status(diagnosis_id, "rejected")
                    return None
                state = self._state_for_user(diagnosis_id, actor_user_id)

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
            if self.workflow_sessions is not None:
                self.workflow_sessions.update_status(diagnosis_id, "completed")
            return diagnosis
