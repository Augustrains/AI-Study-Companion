from collections import defaultdict
from typing import Iterable

from .models import KnowledgePointResult, Question


class AssessmentService:
    """确定性评分服务；正式题库和规则最终应由内容/研发共同维护。"""

    def evaluate(
        self, questions: Iterable[Question], answers: dict[str, str]
    ) -> tuple[list[KnowledgePointResult], list[dict[str, str | bool]]]:
        grouped: dict[str, list[tuple[Question, bool]]] = defaultdict(list)
        answer_records: list[dict[str, str | bool]] = []

        for question in questions:
            submitted = answers.get(question.id, "")
            is_correct = self._normalize(submitted) == self._normalize(question.answer)
            grouped[question.knowledge_point_id].append((question, is_correct))
            answer_records.append(
                {
                    "question_id": question.id,
                    "submitted_answer": submitted,
                    "is_correct": is_correct,
                    "source": question.source,
                }
            )

        results: list[KnowledgePointResult] = []
        for knowledge_point_id, items in grouped.items():
            correct = sum(is_correct for _, is_correct in items)
            total = len(items)
            results.append(
                KnowledgePointResult(
                    knowledge_point_id=knowledge_point_id,
                    ai_status=self._status_for(correct / total),
                    correct=correct,
                    total=total,
                )
            )
        return results, answer_records

    @staticmethod
    def _normalize(value: str) -> str:
        return "".join(value.strip().lower().split())

    @staticmethod
    def _status_for(accuracy: float) -> str:
        if accuracy < 0.4:
            return "不会"
        if accuracy < 0.7:
            return "基本了解"
        if accuracy < 0.9:
            return "熟悉"
        return "掌握"
