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
from modules.memory.module import MemoryModule

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
    memory: MemoryModule | None = None,
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
        # answered_question_ids / diagnosis_round 是必填字段，之前这里漏传，
        # 导致 load_questions 直接抛 TypeError、整个诊断起不来。
        # 它们同时也是选题上下文：让模型知道这是第几轮复测、哪些题已经做过，
        # 而不只是在取题时把旧题过滤掉。
        plan = diagnostic_agent.plan_questions(
            QuestionPlanningInput(
                learning_goal=state.get("learning_goal", ""),
                knowledge_point_mastery=state.get("knowledge_point_mastery", {}),
                knowledge_point_memory=state.get("knowledge_point_memory", {}),
                answered_question_ids=list(state.get("answered_question_ids", []) or []),
                diagnosis_round=int(state.get("diagnosis_round", 1) or 1),
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
            # 复测时优先出没做过的题；题池用完才回收
            exclude_question_ids=set(state.get("answered_question_ids", []) or []),
            rotation_seed=f"{state.get('user_id', '')}:{state.get('book_id', '')}:{state.get('diagnosis_round', 1)}",
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
        current_states = {}
        if memory:
            current_states = {
                item.knowledge_point_id: {
                    "masteryScore": item.mastery_score,
                    "evidenceSummary": item.evidence_summary.to_rule_payload(),
                }
                for item in memory.get_learner_memory(state["user_id"], state["book_id"]).knowledge_points
            }
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
        memory: MemoryModule | None = None,
        learning_record: LearningRecordModule | None = None,
        checkpointer: Any | None = None,
        knowledge_point_catalog: Any | None = None,
    ) -> None:
        self.result_store = result_store
        self.memory = memory
        self.learning_record = learning_record
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

    def _state(self, diagnosis_id: str) -> DiagnosisState:
        state = self.graph.get_state(self._config(diagnosis_id)).values
        if not state:
            raise ResourceNotFoundError(
                f"diagnosis not found: {diagnosis_id}",
                details={"resource": "diagnosis", "diagnosis_id": diagnosis_id},
            )
        return state

    def start_diagnosis(self, *, user_id: str, book_id: str, learning_goal: str) -> dict[str, Any]:
        values = parse_start_fields(user_id, book_id, learning_goal)
        diagnosis_id = f"diag_{uuid4().hex[:10]}"
        self.start(
            diagnosis_id=diagnosis_id,
            user_id=values["user_id"],
            book_id=values["book_id"],
            learning_goal=values["learning_goal"],
        )
        return {"diagnostic_id": diagnosis_id, "questions": self._state(diagnosis_id)["questions"]}

    def _answered_question_history(self, user_id: str, book_id: str) -> tuple[list[str], int]:
        """
        从学习记录里读出该用户在这本书上做过的题目 ID 和已完成的诊断轮次。
        用于复测选题时排除旧题；学习记录不可用时退化为空集（照旧出题，不报错）。
        """
        if not self.learning_record:
            return [], 1
        try:
            page = self.learning_record.list_activities(user_id, category="diagnostic", page=1, page_size=100)
        except Exception:
            return [], 1
        answered: list[str] = []
        rounds = 0
        for activity in page.get("records", []):
            if activity.book_id not in {book_id, {"ml": "ml-001", "dl": "dl-001"}.get(book_id, book_id)}:
                continue
            rounds += 1
            for record in activity.detail.get("answer_records", []) or []:
                question_id = str(record.get("question_id", "")) if isinstance(record, dict) else ""
                if question_id:
                    answered.append(question_id)
        return answered, rounds + 1

    def start(self, *, diagnosis_id: str, user_id: str, book_id: str, learning_goal: str) -> dict[str, Any]:
        learner_memory = self.memory.get_learner_memory(user_id, book_id) if self.memory else None
        answered_question_ids, diagnosis_round = self._answered_question_history(user_id, book_id)
        mastery = (
            {item.knowledge_point_id: item.mastery_level for item in learner_memory.knowledge_points}
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
        self.graph.invoke(
            {
                "diagnosis_id": diagnosis_id,
                "user_id": user_id,
                "book_id": book_id,
                "learning_goal": learning_goal,
                "knowledge_point_mastery": mastery,
                "knowledge_point_memory": memory_by_point,
                "answered_question_ids": answered_question_ids,
                "diagnosis_round": diagnosis_round,
                "status": "started",
            },
            config=self._config(diagnosis_id),
        )
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
            if self.learning_record:
                self.learning_record.record_completed_diagnosis(diagnosis)
            if self.memory:
                self.memory.ingest_diagnosis(diagnosis)
        return diagnosis

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
