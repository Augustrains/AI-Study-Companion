"""Question-bank loading and domain conversion."""

from __future__ import annotations

import json
from pathlib import Path
from collections import defaultdict
from typing import Iterable

from modules.common import api as common_api

from .models import Question, QuestionOption, QuestionSet


class QuestionBank:
    """Load question-bank resources and convert them into domain questions."""

    DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "02-内容与数据" / "data"

    def __init__(self, questions_dir: str | Path | None = None) -> None:
        self.questions_dir = Path(questions_dir) if questions_dir is not None else self.DEFAULT_DIR
    
    #获取题目
    def get_questions(
        self,
        book_id: str,  
        learning_goal: str = "",  #学习目标
        mastered_skill_ids: Iterable[str] = (), #用户已经掌握的知识点 ID
        *,
        max_questions_per_skill: int = 4,  #每个知识点最多选多少道题
    ) -> QuestionSet:
        """
        Read a question bank and convert it to ``Question`` objects.

        ``learning_goal`` is reserved as the future question-filter marker.
        It is intentionally unused for now; questions are selected by
        ``book_id`` only.
        """
        del learning_goal
        json_questions = self._read_json_questions(book_id, mastered_skill_ids, max_questions_per_skill)
        if json_questions is not None:
            return json_questions
        book_id = {"machine_learning": "ml-001", "deep_learning": "dl-001"}.get(book_id, book_id)
        books = self._read_csv("book_catalog.csv")
        if book_id not in {row["book_id"] for row in books}:
            raise common_api.errors.ResourceNotFoundError(
                f"book not found: {book_id}", details={"resource": "book", "book_id": book_id}
            )
        
        #获取教材范围内的知识点
        scope = [row for row in self._read_csv("book_knowledge_scope.csv") if row["book_id"] == book_id and row.get("status") == "active"]
        scoped_skills = {row["knowledge_point_id"] for row in scope}
        mastered = set(mastered_skill_ids)
        #排除已经掌握的知识点
        selected_skills = scoped_skills - mastered

        questions = self._read_question_rows(book_id)
        #读取题目与其他实体之间的关系
        question_knowledge = self._edges("question_knowledge_edges.csv", "question_id", "knowledge_point_id")
        question_abilities = self._edges("question_ability_edges.csv", "question_id", "ability_id")
        question_sections = self._edges("question_section_edges.csv", "question_id", "section_id")
        sections = {row["section_id"]: row for row in self._read_csv("section_catalog.csv")}
        selected: list[dict] = []
        counts: dict[str, int] = defaultdict(int)
        #题目筛选逻辑
        for row in questions:
            #只选择已审核题目
            if row.get("status") != "approved":
                continue
            #获取题目关联的知识点
            qid = row["question_id"]
            all_knowledge_ids = question_knowledge.get(qid, [])
            knowledge_ids = [item for item in all_knowledge_ids if item in selected_skills]
            #排除不完全匹配的题目
            if not knowledge_ids or set(all_knowledge_ids) - selected_skills:
                continue
            #限制每个知识点的题目数量
            if any(counts[item] >= max_questions_per_skill for item in knowledge_ids):
                continue
            selected.append(row)
            for item in knowledge_ids:
                counts[item] += 1
        #格式转换，变成Question对象
        parsed = [self._parse_question(row, question_knowledge, question_abilities, question_sections, sections) for row in selected]
        return QuestionSet(
            questions=parsed,
            correct_answers={row["question_id"]: row["correct_option"] for row in selected},
            selected_skill_ids=sorted(selected_skills),
        )

    def _read_json_questions(
        self,
        book_id: str,
        mastered_skill_ids: Iterable[str],
        max_questions_per_skill: int,
    ) -> QuestionSet | None:
        """Load the compact JSON question resources used by local demos/tests."""
        normalized = {"ml-001": "machine_learning", "dl-001": "deep_learning"}.get(book_id, book_id)
        path = self.questions_dir / f"{normalized}.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise common_api.errors.StorageReadError(f"question resource cannot be read: {path}") from exc
        mastered = set(mastered_skill_ids)
        counts: dict[str, int] = defaultdict(int)
        questions: list[Question] = []
        correct_answers: dict[str, str] = {}
        for item in payload.get("questions", []):
            tag = str(item.get("tag", ""))
            if not tag or tag in mastered or counts[tag] >= max_questions_per_skill:
                continue
            options = [QuestionOption(id=str(option["id"]), text=str(option["text"])) for option in item.get("options", [])]
            question = Question(
                id=str(item["id"]),
                title=str(item.get("title", "")),
                tag=tag,
                book_id=str(payload.get("book_id", book_id)),
                knowledge_point_ids=[tag],
                options=options,
                source=str(item.get("source", "")),
            )
            questions.append(question)
            correct_answers[question.id] = str(item.get("correct_option_id", ""))
            counts[tag] += 1
        return QuestionSet(
            questions=questions,
            correct_answers=correct_answers,
            selected_skill_ids=sorted({question.tag for question in questions}),
        )

    def _read_question_rows(self, book_id: str) -> list[dict]:
        return [row for row in self._read_csv("question_bank.csv") if row.get("book_id") == book_id]

    def _read_csv(self, name: str) -> list[dict[str, str]]:
        path = self.questions_dir / name
        return common_api.csv_storage.CsvContentReader(path).read()

    def _edges(self, name: str, left: str, right: str) -> dict[str, list[str]]:
        result: dict[str, list[str]] = defaultdict(list)
        for row in self._read_csv(name):
            if row.get("status") == "active" and row.get(left) and row.get(right):
                result[row[left]].append(row[right])
        return result

    @staticmethod
    def _parse_question(item: dict, knowledge_edges: dict[str, list[str]], ability_edges: dict[str, list[str]], section_edges: dict[str, list[str]], sections: dict[str, dict[str, str]]) -> Question:
        question_id = item["question_id"]
        knowledge_ids = knowledge_edges.get(question_id, [])
        ability_ids = ability_edges.get(question_id, [])
        section_ids = section_edges.get(question_id, [])
        chapter_ids = {sections[item]["chapter_id"] for item in section_ids if item in sections}
        options = json.loads(item["options_json"])
        options = [{"id": str(index), "text": value} for index, value in enumerate(options)] if options and isinstance(options[0], str) else options
        options = [
            QuestionOption(id=option["id"], text=option["text"])
            for option in options
        ]
        return Question(
            id=question_id,
            title=item["prompt"],
            tag=knowledge_ids[0] if knowledge_ids else "",
            options=options,
            source=item.get("source_note", ""),
            book_id=item.get("book_id", ""),
            chapter_id=next(iter(chapter_ids), ""),
            section_ids=section_ids,
            knowledge_point_ids=knowledge_ids,
            ability_ids=ability_ids,
            difficulty=item.get("difficulty", ""),
        )
