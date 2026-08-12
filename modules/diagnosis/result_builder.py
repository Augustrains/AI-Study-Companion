"""诊断结果构造服务。

把题目作答、知识点统计和最终诊断对象的组装集中在一个地方，避免
API 门面、LangGraph 工作流和记忆模块分别重复拼装诊断结果。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import DiagnosisResult, KnowledgePointResult, STATUSES


class DiagnosisResultBuilder:
    """从诊断会话和评估草稿构造统一的诊断结果。"""

    @staticmethod
    def question_results(session: Any) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
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
                }
            )
        return records

    @staticmethod
    def summary(session: Any, draft_results: list[dict[str, Any]], analysis: Any) -> dict[str, Any]:
        records = DiagnosisResultBuilder.question_results(session)
        answered = sum(not item["skipped"] for item in records)
        correct = sum(bool(item["is_correct"]) for item in records)
        total = len(records)
        statuses = [item.get("ai_status") for item in draft_results if item.get("ai_status") in STATUSES]
        level = max(statuses, key=STATUSES.index) if statuses else STATUSES[0]
        accuracy = round(correct / total * 100) if total else 0
        return {
            "level": level,
            "accuracy": f"{accuracy}%",
            "confidence": "high" if answered >= len(session.questions) else "medium",
            "evidence": analysis.evidence,
            "answer_performance": analysis.answer_performance,
            "generated_at": datetime.now().astimezone().isoformat(),
            "related_scope": f"{session.learning_goal}及其前置知识点。",
        }

    @staticmethod
    def final(
        session: Any,
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
            answer_records=DiagnosisResultBuilder.question_results(session),
        )
