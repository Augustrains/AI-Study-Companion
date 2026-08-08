from __future__ import annotations

from typing import Any
from uuid import uuid4

from .agent import DiagnosticAgent
from .models import DiagnosisResult, LearningSession, Question, STATUSES
from .question_repository import QuestionRepository
from .service import AssessmentService
from .session_repository import InMemoryLearningSessionRepository
from .workflow import DiagnosisWorkflow


class DiagnosisModule:
    """Application facade adapting HTTP-friendly actions to the workflow."""

    def __init__(self, workflow: DiagnosisWorkflow, question_repository: QuestionRepository, sessions: InMemoryLearningSessionRepository) -> None:
        self.workflow = workflow
        self.question_repository = question_repository
        self.sessions = sessions
        self._answers: dict[str, dict[str, str]] = {}
        self._questions: dict[str, list[Question]] = {}

    def start(self, *, user_id: str, book_id: str, learning_goal: str) -> dict[str, Any]:
        session = LearningSession(
            id=f"session_{uuid4().hex[:10]}",
            user_id=user_id,
            book_id=book_id,
            learning_goal=learning_goal,
        )
        questions = self.question_repository.get_diagnosis_questions(book_id, learning_goal)
        pending = self.workflow.start(session)
        diagnosis_id = pending["diagnosis_id"]
        self._questions[diagnosis_id] = questions
        self._answers[diagnosis_id] = {}
        return {
            "diagnostic_id": diagnosis_id,
            "questions": [
                {
                    "id": question.id,
                    "title": question.question,
                    "tag": question.knowledge_point_id,
                    "options": [{"id": str(index), "text": option} for index, option in enumerate(question.options)],
                }
                for question in questions
            ],
        }

    def submit_answer(self, diagnosis_id: str, question_id: str, answer: str, skipped: bool = False) -> dict[str, Any]:
        questions = self._questions[diagnosis_id]
        question = next((item for item in questions if item.id == question_id), None)
        if question is None:
            raise KeyError(f"unknown question: {question_id}")
        if not skipped:
            try:
                answer = question.options[int(answer)]
            except (ValueError, IndexError):
                raise ValueError(f"invalid answer for question: {question_id}") from None
        self._answers[diagnosis_id][question_id] = "" if skipped else answer
        return {"diagnostic_id": diagnosis_id, "question_id": question_id, "saved": True}

    def finish(self, diagnosis_id: str) -> dict[str, Any]:
        draft = self.workflow.submit(diagnosis_id, self._answers[diagnosis_id])
        results = draft.get("draft_results", [])
        state = self.workflow.graph.get_state(self.workflow._config(diagnosis_id)).values
        records = state.get("answer_records", [])
        total = len(records)
        correct = sum(bool(item.get("is_correct")) for item in records)
        statuses = [item.get("ai_status") for item in results]
        level = max(statuses, key=lambda value: STATUSES.index(value)) if statuses else "未测评"
        return {
            "diagnostic_id": diagnosis_id,
            "level": level,
            "accuracy": f"{round(correct / total * 100)}%" if total else "0%",
            "confidence": "高" if total and total >= len(self._questions[diagnosis_id]) else "中",
            "evidence": "题目作答结果以及关联知识点表现。",
            "suggestions": [item.get("explanation", "") for item in results if item.get("explanation")],
            "draft_results": results,
        }

    def review(self, diagnosis_id: str, *, calibration: str = "same", reason: str = "") -> DiagnosisResult | None:
        del reason  # The current domain model has no separate calibration-reason field.
        state = self.workflow.graph.get_state(self.workflow._config(diagnosis_id)).values
        results = state.get("draft_results", [])
        statuses = STATUSES[1:]
        calibrations: dict[str, str] = {}
        if calibration != "same":
            delta = -1 if calibration == "lower" else 1
            for item in results:
                current = item["ai_status"]
                index = max(0, min(len(statuses) - 1, statuses.index(current) + delta))
                calibrations[item["knowledge_point_id"]] = statuses[index]
        return self.workflow.review(
            diagnosis_id,
            action="edit" if calibrations else "approve",
            calibrations=calibrations,
        )
