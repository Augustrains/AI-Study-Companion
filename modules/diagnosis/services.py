"""Application and domain services for the diagnosis module.

The workflow owns orchestration and LangGraph state transitions.  This module
owns reusable diagnosis operations so graph nodes do not contain business
rules or persistence details.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Iterable

from modules.common import api as common_api
from modules.common.errors import ResourceNotFoundError

from .agent import DiagnosticAnalysisOutput
from .mastery_rules_adapter import calculate_mastery_update
from .models import (
    DiagnosticSession,
    DiagnosisResult,
    KnowledgePointResult,
    Question,
    QuestionOption,
    QuestionSet,
    STATUSES,
)


def _task_context_for_mode(base: dict[str, Any] | None, planned_mode: str) -> dict[str, Any]:
    context = dict(base or {})
    mode = planned_mode or str(context.get("task_mode", "diagnostic"))
    context["task_mode"] = mode
    context["is_delayed_retrieval"] = mode == "retrieval"
    return context


class QuestionBank:
    """Load, filter, and convert diagnosis question-bank data."""

    DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "02-内容与数据" / "data"
    BOOK_ALIASES = {"machine_learning": "ml-001", "deep_learning": "dl-001"}

    def __init__(self, questions_dir: str | Path | None = None) -> None:
        self.questions_dir = Path(questions_dir) if questions_dir is not None else self.DEFAULT_DIR

    def get_question_inventory(self, book_id: str) -> dict[str, int]:
        """Return selectable question counts grouped by knowledge point."""

        normalized_book_id = self.BOOK_ALIASES.get(book_id, book_id)
        normalized = {"ml-001": "machine_learning", "dl-001": "deep_learning"}.get(normalized_book_id, normalized_book_id)
        json_path = self.questions_dir / f"{normalized}.json"
        if json_path.exists():
            try:
                payload = json.loads(json_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise common_api.errors.StorageReadError(f"question resource cannot be read: {json_path}") from exc
            counts: dict[str, int] = defaultdict(int)
            for item in payload.get("questions", []):
                point_id = str(item.get("tag", ""))
                if point_id:
                    counts[point_id] += 1
            return dict(sorted(counts.items()))

        knowledge_edges = self._edges("question_knowledge_edges.csv", "question_id", "knowledge_point_id")
        counts: dict[str, int] = defaultdict(int)
        for row in self._read_question_rows(normalized_book_id):
            if row.get("status") != "approved":
                continue
            for point_id in knowledge_edges.get(row["question_id"], []):
                counts[point_id] += 1
        return dict(sorted(counts.items()))

    #筛选获得问题
    def get_questions(
        self,
        book_id: str,  #教材
        learning_goal: str = "",   #目标
        knowledge_point_mastery: dict[str, str] | None = None,
        *,
        max_questions_per_knowledge_point: int = 4,   #限制每个知识点最多生成几道题
        # TODO(task-context): 后续由学习任务模块传入 task_mode、复习间隔等上下文。
        task_context: dict[str, Any] | None = None,
        question_plan: dict[str, dict[str, Any]] | None = None,
    ) -> "QuestionSet":
        del learning_goal
        normalized_book_id = self.BOOK_ALIASES.get(book_id, book_id)
        mastery = knowledge_point_mastery or {}
        json_questions = self._read_json_questions(normalized_book_id, mastery, max_questions_per_knowledge_point, task_context, question_plan)
        if json_questions is not None:
            return json_questions

        if normalized_book_id not in {row["book_id"] for row in self._read_csv("book_catalog.csv")}:
            raise common_api.errors.ResourceNotFoundError(
                f"book not found: {normalized_book_id}",
                details={"resource": "book", "book_id": normalized_book_id},
            )

        mastered = {key for key, level in mastery.items() if level == "掌握"}
        scope = {
            row["knowledge_point_id"]
            for row in self._read_csv("book_knowledge_scope.csv")
            if row["book_id"] == normalized_book_id and row.get("status") == "active"
        }
        selected_knowledge_points = (
            {point_id for point_id, item in question_plan.items() if int(item.get("question_count", 0)) > 0}
            if question_plan is not None
            else scope - mastered
        )
        knowledge_edges = self._edges("question_knowledge_edges.csv", "question_id", "knowledge_point_id")
        ability_edges = self._edges("question_ability_edges.csv", "question_id", "ability_id")
        section_edges = self._edges("question_section_edges.csv", "question_id", "section_id")
        sections = {row["section_id"]: row for row in self._read_csv("section_catalog.csv")}
        counts: dict[str, int] = defaultdict(int)
        selected: list[dict[str, str]] = []

        for row in self._read_question_rows(normalized_book_id):
            if row.get("status") != "approved":
                continue
            question_id = row["question_id"]
            all_knowledge_ids = knowledge_edges.get(question_id, [])
            knowledge_ids = [item for item in all_knowledge_ids if item in selected_knowledge_points]
            if not knowledge_ids or set(all_knowledge_ids) - selected_knowledge_points:
                continue
            if any(
                counts[item] >= (
                    min(int(question_plan[item].get("question_count", 0)), max_questions_per_knowledge_point)
                    if question_plan is not None
                    else max_questions_per_knowledge_point
                )
                for item in knowledge_ids
            ):
                continue
            selected.append(row)
            for item in knowledge_ids:
                counts[item] += 1

        questions = [self._parse_question(row, knowledge_edges, ability_edges, section_edges, sections, task_context, question_plan) for row in selected]
        return QuestionSet(
            questions=questions,
            correct_answers={row["question_id"]: row["correct_option"] for row in selected},
            selected_knowledge_point_ids=sorted(selected_knowledge_points),
        )

    def _read_json_questions(self, book_id: str, knowledge_point_mastery: dict[str, str], max_questions_per_knowledge_point: int, task_context: dict[str, Any] | None = None, question_plan: dict[str, dict[str, Any]] | None = None) -> "QuestionSet | None":
        normalized = {"ml-001": "machine_learning", "dl-001": "deep_learning"}.get(book_id, book_id)
        path = self.questions_dir / f"{normalized}.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise common_api.errors.StorageReadError(f"question resource cannot be read: {path}") from exc

        mastered = {key for key, level in knowledge_point_mastery.items() if level == "掌握"}
        counts: dict[str, int] = defaultdict(int)
        questions: list[Question] = []
        correct_answers: dict[str, str] = {}
        for item in payload.get("questions", []):
            tag = str(item.get("tag", ""))
            limit = (
                min(int(question_plan.get(tag, {}).get("question_count", 0)), max_questions_per_knowledge_point)
                if question_plan is not None
                else max_questions_per_knowledge_point
            )
            if not tag or (question_plan is None and tag in mastered) or counts[tag] >= limit:
                continue
            planned_mode = str(question_plan.get(tag, {}).get("task_mode", "")) if question_plan is not None else ""
            question = Question(
                id=str(item["id"]),
                title=str(item.get("title", "")),
                tag=tag,
                book_id=str(payload.get("book_id", book_id)),
                knowledge_point_ids=[tag],
                options=[QuestionOption(id=str(option["id"]), text=str(option["text"])) for option in item.get("options", [])],
                source=str(item.get("source", "")),
                task_mode=planned_mode or "diagnostic",
                task_context=_task_context_for_mode(task_context, planned_mode),
            )
            questions.append(question)
            correct_answers[question.id] = str(item.get("correct_option_id", ""))
            counts[tag] += 1
        return QuestionSet(
            questions=questions,
            correct_answers=correct_answers,
            selected_knowledge_point_ids=sorted({question.tag for question in questions}),
        )

    def _read_question_rows(self, book_id: str) -> list[dict[str, str]]:
        return [row for row in self._read_csv("question_bank.csv") if row.get("book_id") == book_id]

    def _read_csv(self, name: str) -> list[dict[str, str]]:
        return common_api.csv_storage.CsvContentReader(self.questions_dir / name).read()

    def _edges(self, name: str, left: str, right: str) -> dict[str, list[str]]:
        result: dict[str, list[str]] = defaultdict(list)
        for row in self._read_csv(name):
            if row.get("status") == "active" and row.get(left) and row.get(right):
                result[row[left]].append(row[right])
        return result

    @staticmethod
    def _parse_question(item: dict[str, str], knowledge_edges: dict[str, list[str]], ability_edges: dict[str, list[str]], section_edges: dict[str, list[str]], sections: dict[str, dict[str, str]], task_context: dict[str, Any] | None = None, question_plan: dict[str, dict[str, Any]] | None = None) -> Question:
        question_id = item["question_id"]
        knowledge_ids = knowledge_edges.get(question_id, [])
        section_ids = section_edges.get(question_id, [])
        chapter_ids = {sections[section_id]["chapter_id"] for section_id in section_ids if section_id in sections}
        options = json.loads(item["options_json"])
        if options and isinstance(options[0], str):
            options = [{"id": str(index), "text": value} for index, value in enumerate(options)]
        planned_mode = next(
            (str(question_plan[point_id].get("task_mode", "")) for point_id in knowledge_ids if question_plan and point_id in question_plan),
            "",
        )
        return Question(
            id=question_id,
            title=item["prompt"],
            tag=knowledge_ids[0] if knowledge_ids else "",
            options=[QuestionOption(id=str(option["id"]), text=str(option["text"])) for option in options],
            source=item.get("source_note", ""),
            book_id=item.get("book_id", ""),
            chapter_id=next(iter(chapter_ids), ""),
            section_ids=section_ids,
            knowledge_point_ids=knowledge_ids,
            ability_ids=ability_edges.get(question_id, []),
            task_mode=planned_mode or "diagnostic",
            task_context=_task_context_for_mode(task_context, planned_mode),
        )


class GeneratedQuestionBank:
    """Load the generated bilingual Quiz catalog."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.items_path = self.root / "题目" / "curriculum_items.jsonl"
        self.localization_path = self.root / "题目" / "quiz_localization_zh_review.csv"
        self.mapping_path = self.root / "题目-知识点映射" / "quiz_knowledge_mapping_candidates.csv"
        self.taxonomy_path = self.root / "题目-教材映射" / "knowledge_taxonomy.json"

    def get_question_inventory(self, book_id: str) -> dict[str, int]:
        """Return generated quiz availability for each mapped knowledge point."""

        target = {"machine_learning": "ml-001", "deep_learning": "dl-001"}.get(book_id, book_id)
        taxonomy = json.loads(self.taxonomy_path.read_text(encoding="utf-8"))
        valid_points = {row["knowledge_point_id"] for row in taxonomy}
        mapping_by_item: dict[str, list[str]] = defaultdict(list)
        for row in self._read_csv(self.mapping_path):
            if row.get("knowledge_point_id") in valid_points:
                mapping_by_item[row.get("learning_item_id", "")].append(row["knowledge_point_id"])
        counts: dict[str, int] = defaultdict(int)
        for line in self.items_path.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            if item.get("item_type") != "quiz_question":
                continue
            repository = item.get("source", {}).get("repository_name", "")
            if {"ML-For-Beginners": "ml-001", "AI-For-Beginners": "dl-001"}.get(repository, "") != target:
                continue
            for point_id in mapping_by_item.get(str(item.get("learning_item_id", "")), []):
                counts[point_id] += 1
        return dict(sorted(counts.items()))

    def get_questions(self, book_id: str, learning_goal: str = "", knowledge_point_mastery: dict[str, str] | None = None, *, max_questions_per_knowledge_point: int = 4, task_context: dict[str, Any] | None = None, question_plan: dict[str, dict[str, Any]] | None = None) -> QuestionSet:
        # TODO(task-context): 生成题目时同步注入 task_mode、延迟回忆和复习间隔等任务上下文。
        del learning_goal
        target = {"machine_learning": "ml-001", "deep_learning": "dl-001"}.get(book_id, book_id)
        taxonomy = json.loads(self.taxonomy_path.read_text(encoding="utf-8"))
        valid_points = {row["knowledge_point_id"] for row in taxonomy}
        mapping_by_item: dict[str, list[str]] = defaultdict(list)
        for row in self._read_csv(self.mapping_path):
            if row.get("knowledge_point_id") in valid_points:
                mapping_by_item[row.get("learning_item_id", "")].append(row["knowledge_point_id"])
        localizations = {row.get("learning_item_id", ""): row for row in self._read_csv(self.localization_path)}
        mastered = {key for key, level in (knowledge_point_mastery or {}).items() if level == "掌握"}
        counts: dict[str, int] = defaultdict(int)
        questions: list[Question] = []
        answers: dict[str, str] = {}
        for line in self.items_path.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            if item.get("item_type") != "quiz_question":
                continue
            repository = item.get("source", {}).get("repository_name", "")
            item_book = {"ML-For-Beginners": "ml-001", "AI-For-Beginners": "dl-001"}.get(repository, "")
            if item_book != target:
                continue
            item_id = str(item.get("learning_item_id", ""))
            points = [
                point
                for point in mapping_by_item.get(item_id, [])
                if (
                    point in question_plan and int(question_plan[point].get("question_count", 0)) > 0
                    if question_plan is not None
                    else point not in mastered
                )
            ]
            if not points or any(
                counts[point] >= (
                    min(int(question_plan[point].get("question_count", 0)), max_questions_per_knowledge_point)
                    if question_plan is not None
                    else max_questions_per_knowledge_point
                )
                for point in points
            ):
                continue
            loc = localizations.get(item_id, {})
            options = item.get("options", [])
            parsed = [QuestionOption(id=str(option.get("key", "")), text=loc.get(f"zh_option_{str(option.get('key', '')).lower()}") or str(option.get("text", ""))) for option in options]
            planned_mode = str(question_plan[points[0]].get("task_mode", "")) if question_plan is not None else ""
            questions.append(Question(id=item_id, title=loc.get("zh_stem") or str(item.get("stem", "")), tag=points[0], book_id=target, knowledge_point_ids=points, task_mode=planned_mode or "diagnostic", task_context=_task_context_for_mode(task_context, planned_mode), options=parsed, source=str(item.get("source", {}).get("source_url", ""))))
            answers[item_id] = next((str(option.get("key", "")) for option in options if option.get("is_correct")), "")
            for point in points:
                counts[point] += 1
        return QuestionSet(questions=questions, correct_answers=answers, selected_knowledge_point_ids=sorted(counts))

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        import csv
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))


class AssessmentService:
    """Evaluate submitted answers and aggregate results by knowledge point."""

    def evaluate(
        self,
        questions: Iterable[Question],
        answers: dict[str, str],
        correct_answers: dict[str, str],
        current_states: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[list[KnowledgePointResult], list[dict[str, Any]]]:
        grouped: dict[str, list[bool]] = defaultdict(list)
        records: list[dict[str, Any]] = []

        for question in questions:
            submitted = answers.get(question.id, "")
            submitted_id = self._to_option_id(question, submitted)
            expected = correct_answers.get(question.id, "")
            is_correct = bool(submitted) and self._normalize(submitted_id) == self._normalize(expected)
            # TODO(task-context): 题目实例携带任务上下文后，从这里读取 task_mode、
            # is_delayed_retrieval 和 scheduled_interval_days，而不是使用诊断默认值。
            task_context = question.task_context or {}
            knowledge_point_ids = question.knowledge_point_ids or ([question.tag] if question.tag else [])
            for knowledge_point_id in knowledge_point_ids:
                grouped[knowledge_point_id].append(is_correct)
            records.append(
                {
                    "question_id": question.id,
                    "submitted_answer": submitted_id,
                    "is_correct": is_correct,
                    "source": question.source,
                    "knowledge_point_ids": knowledge_point_ids,
                    "score": 1.0 if is_correct else 0.0,
                    "evidence_id": f"{question.id}:answer",
                    "evidence_strength": task_context.get("evidence_strength", "direct"),
                    "task_mode": task_context.get("task_mode", "diagnostic"),
                    "hint_count": int(task_context.get("hint_count", 0)),
                    "retry_count": int(task_context.get("retry_count", 0)),
                    "is_independent": bool(task_context.get("is_independent", True)),
                    "is_delayed_retrieval": bool(task_context.get("is_delayed_retrieval", False)),
                    "scheduled_interval_days": task_context.get("scheduled_interval_days"),
                    "occurred_at": datetime.now().astimezone().isoformat(),
                }
            )

        results: list[KnowledgePointResult] = []
        states = current_states or {}
        records_by_point: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            for knowledge_point_id in record["knowledge_point_ids"]:
                records_by_point[knowledge_point_id].append(record)
        for knowledge_point_id, values in grouped.items():
            point_records = records_by_point[knowledge_point_id]
            update = calculate_mastery_update(
                {
                    "currentState": states.get(knowledge_point_id, {}),
                    "evidence": [
                        {
                            "evidenceId": f"{record['evidence_id']}:{knowledge_point_id}",
                            "score": record["score"],
                            "isCorrect": record["is_correct"],
                            "evidenceStrength": record["evidence_strength"],
                            "taskMode": record["task_mode"],
                            "hintCount": record["hint_count"],
                            "retryCount": record["retry_count"],
                            "isIndependent": record["is_independent"],
                            "isDelayedRetrieval": record["is_delayed_retrieval"],
                            "occurredAt": record["occurred_at"],
                        }
                        for record in point_records
                    ],
                }
            )
            results.append(
                KnowledgePointResult(
                    knowledge_point_id=knowledge_point_id,
                    ai_status=update["masteryLevel"],
                    correct=sum(values),
                    total=len(values),
                    mastery_score=update["masteryScore"],
                    memory_status=update["memoryStatus"],
                    memory_stability_days=update["memoryStabilityDays"],
                    confidence=update["confidence"],
                    evidence_ids=update["evidenceIds"],
                    evidence_summary=update["evidenceSummary"],
                    reason_codes=update["reasonCodes"],
                    algorithm_name=update["algorithmName"],
                    algorithm_version=update["algorithmVersion"],
                    next_review_at=update["nextReviewAt"],
                )
            )
        return results, records

    @staticmethod
    def _to_option_id(question: Question, answer: str) -> str:
        option_ids = {option.id for option in question.options}
        if answer in option_ids:
            return answer
        normalized = AssessmentService._normalize(answer)
        return next(
            (option.id for option in question.options if AssessmentService._normalize(option.text) == normalized),
            answer,
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return "".join(value.strip().lower().split())

class DiagnosticSessionStore:
    """Repository for diagnostic runs.

    This is intentionally an in-memory implementation for the demo.  The
    workflow depends on this small contract, so it can later be replaced by a
    database or Redis repository without changing the workflow.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, DiagnosticSession] = {}

    def save(self, session: DiagnosticSession) -> None:
        self._sessions[session.id] = session

    def get(self, session_id: str) -> DiagnosticSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise ResourceNotFoundError(
                f"diagnostic session not found: {session_id}",
                details={"resource": "diagnostic_session", "session_id": session_id},
            ) from exc


class DiagnosisService:
    """Reusable transformations and commit operations for diagnosis runs."""

    @staticmethod
    def questions_from_state(items: list[dict[str, Any]]) -> list[Question]:
        return [
            Question(
                id=item["id"],
                title=item["title"],
                tag=item["tag"],
                book_id=item.get("book_id", ""),
                chapter_id=item.get("chapter_id", ""),
                section_ids=item.get("section_ids", []),
                knowledge_point_ids=item.get("knowledge_point_ids", []),
                ability_ids=item.get("ability_ids", []),
                task_mode=item.get("task_mode", "diagnostic"),
                task_context=item.get("task_context", {}),
                options=[QuestionOption(**option) for option in item.get("options", [])],
                source=item.get("source", ""),
            )
            for item in items
        ]

    @staticmethod
    def question_payload(question: Question) -> dict[str, Any]:
        return {
            "id": question.id,
            "title": question.title,
            "tag": question.tag,
            "book_id": question.book_id,
            "chapter_id": question.chapter_id,
            "section_ids": question.section_ids,
            "knowledge_point_ids": question.knowledge_point_ids,
            "ability_ids": question.ability_ids,
            "task_mode": question.task_mode,
            "task_context": question.task_context,
            "source": question.source,
            "options": [{"id": option.id, "text": option.text} for option in question.options],
        }

    @classmethod
    def question_records(cls, session: DiagnosticSession) -> list[dict[str, Any]]:
        records = []
        for question in session.questions:
            question_id = question["id"]
            submitted = session.answers.get(question_id, "")
            records.append(
                {
                    "question_id": question_id,
                    "title": question["title"],
                    "knowledge_point_id": question.get("tag", ""),
                    "knowledge_point_ids": question.get("knowledge_point_ids", [question.get("tag", "")]),
                    "ability_ids": question.get("ability_ids", []),
                    "chapter_id": question.get("chapter_id", ""),
                    "section_ids": question.get("section_ids", []),
                    "submitted_answer": submitted,
                    "correct_answer": session.correct_answers.get(question_id, ""),
                    "is_correct": bool(submitted) and submitted == session.correct_answers.get(question_id, ""),
                    "skipped": question_id in session.answers and submitted == "",
                    **session.answer_metadata.get(question_id, {}),
                }
            )
        return records

    @classmethod
    def summary(
        cls,
        session: DiagnosticSession,
        draft_results: list[dict[str, Any]],
        analysis: DiagnosticAnalysisOutput,
    ) -> dict[str, Any]:
        records = cls.question_records(session)
        total = len(records)
        answered = sum(not item["skipped"] for item in records)
        correct = sum(bool(item["is_correct"]) for item in records)
        statuses = [item["ai_status"] for item in draft_results if item.get("ai_status") in STATUSES]
        level = max(statuses, key=STATUSES.index) if statuses else STATUSES[0]
        accuracy = round(correct / total * 100) if total else 0
        return {
            "level": level,
            "accuracy": f"{accuracy}%",
            "confidence": "high" if answered >= len(session.questions) else "medium",
            "evidence": analysis.evidence,
            "answer_performance": analysis.answer_performance,
            "generated_at": datetime.now().astimezone().isoformat(),
            "related_scope": f"{session.learning_goal}及其前置知识点",
        }

    @classmethod
    def final_result(
        cls,
        session: DiagnosticSession,
        draft_results: list[dict[str, Any]],
        calibrations: dict[str, str] | None = None,
    ) -> DiagnosisResult:
        calibrations = calibrations or {}
        results = [KnowledgePointResult(**item) for item in draft_results]
        for result in results:
            result.calibrated_status = calibrations.get(result.knowledge_point_id)
        return DiagnosisResult(
            diagnosis_id=session.id,
            user_id=session.user_id,
            book_id=session.book_id,
            learning_goal=session.learning_goal,
            results=results,
            answer_records=cls.question_records(session),
        )
