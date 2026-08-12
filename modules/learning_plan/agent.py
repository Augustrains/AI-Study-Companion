"""学习计划生成代理。

负责把诊断阶段产生的可靠事实转换为前端可直接展示的学习计划。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any


class LearningPlanAgent:
    """根据诊断会话上下文生成学习建议和学习资源。

    当前实现使用确定性规则，计划决策集中在后端，前端只负责展示结果。
    """

    def build(self, context: dict[str, Any]) -> dict[str, Any]:
        """整理上下文，并组装完整的学习计划响应。"""
        # 复制列表，避免生成计划时意外修改诊断会话中的原始数据。
        results = list(context.get("diagnosis_results", []))
        records = list(context.get("answer_records", []))
        questions = {str(item["id"]): item for item in context.get("questions", [])}
        tasks = [self._add_schedule(task) for task in context.get("tasks", [])]
        accuracy = self._accuracy(records)
        weak_results = sorted(results, key=self._result_score)

        return {
            "book": context["book"],
            "goal": context["goal"],
            "goalLevel": context["goal_level"],
            "tasks": tasks,
            "advice": self._build_advice(weak_results, records, questions, accuracy),
            "resources": self._build_resources(weak_results, records, questions),
        }

    @staticmethod
    def _add_schedule(task: dict[str, Any]) -> dict[str, Any]:
        """为任务生成预计完成日期；当前默认全部安排在当天。"""
        scheduled = dict(task)
        scheduled.setdefault("expected_completion_date", date.today().isoformat())
        return scheduled

    @staticmethod
    def _accuracy(records: list[dict[str, Any]]) -> int:
        """计算已作答题目的百分制正确率，跳过主动跳过的题目。"""
        answered = [item for item in records if not item.get("skipped")]
        if not answered:
            return 0
        return round(sum(bool(item.get("is_correct")) for item in answered) / len(answered) * 100)

    @staticmethod
    def _result_score(result: dict[str, Any]) -> tuple[int, float]:
        """生成排序键：薄弱状态优先，同状态下正确率较低者优先。"""
        status = result.get("calibrated_status") or result.get("ai_status") or ""
        correct = int(result.get("correct", 0))
        total = int(result.get("total", 0))
        return (0 if status in {"不会", "基本了解"} else 1, correct / total if total else 0)

    def _build_advice(
        self,
        weak_results: list[dict[str, Any]],
        records: list[dict[str, Any]],
        questions: dict[str, dict[str, Any]],
        accuracy: int,
    ) -> list[str]:
        """根据薄弱知识点、漏答情况和整体正确率生成文字建议。"""
        advice: list[str] = []
        if weak_results:
            weakest = weak_results[0]
            name = str(weakest.get("knowledge_point_id", "当前薄弱知识点"))
            advice.append(f"诊断正确率为 {accuracy}%；优先学习“{name}”，再进行针对性复测。")
        skipped = sum(1 for item in records if item.get("skipped") or not item.get("submitted_answer"))
        if skipped:
            advice.append(f"本次诊断有 {skipped} 道题未完成，建议先补齐对应题目。")
        if records and not advice:
            advice.append(f"本次诊断正确率为 {accuracy}%，建议继续完成计划中的下一项任务。")
        if not advice and questions:
            advice.append("当前诊断信息不足，建议先完成一轮诊断题。")
        return advice

    def _build_resources(
        self,
        weak_results: list[dict[str, Any]],
        records: list[dict[str, Any]],
        questions: dict[str, dict[str, Any]],
    ) -> list[dict[str, str]]:
        """从诊断答题记录中提取与薄弱知识点相关的学习资料。"""
        weak_ids = {str(item.get("knowledge_point_id")) for item in weak_results[:3]}
        grouped: dict[str, dict[str, str]] = {}
        for record in records:
            # 题目标签用于把答题记录关联回诊断结果中的知识点。
            question = questions.get(str(record.get("question_id")), {})
            knowledge_point_id = str(question.get("tag", ""))
            source = str(record.get("source", "")).strip()
            if not source or (weak_ids and knowledge_point_id not in weak_ids):
                continue
            # 资源来源通常以“章节/小节”的形式保存，拆分后生成标题和位置。
            parts = [part.strip() for part in source.split("/") if part.strip()]
            title = parts[-1] if parts else source
            location = " / ".join(parts[:-1]) if len(parts) > 1 else source
            grouped[source] = {
                "id": f"diagnostic-source-{len(grouped) + 1}",
                "type": "教材",
                "title": title,
                "location": location,
                "excerpt": f"该资料来自诊断题关联来源，用于复习“{knowledge_point_id}”。",
            }
        return list(grouped.values())
