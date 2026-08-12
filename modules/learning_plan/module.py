"""学习计划领域模块。

负责校验诊断会话状态、生成学习任务，并调用代理生成建议与资源。
"""

from __future__ import annotations

from pathlib import Path
import csv
from typing import Any
from uuid import uuid4

from modules.common.errors import ValidationAppError, WorkflowStateError
from modules.diagnosis.diagnosis_workflow import DiagnosticSessionStore
from modules.diagnosis.models import STATUSES
from modules.common import api as common_api

from .agent import LearningPlanAgent

if False:  # pragma: no cover
    from modules.memory.module import MemoryModule


# 前端使用的教材编号与诊断题库编号之间的映射。
BOOK_TO_QUESTION_BANK = {"ml": "ml-001", "dl": "dl-001"}

# 诊断结果中的知识点编号到用户可读名称的映射。
KNOWLEDGE_POINT_NAMES = {
    "supervised_learning": "监督学习",
    "linear_regression": "线性回归",
    "model_evaluation": "模型评估",
    "overfitting": "过拟合与泛化",
    "deep_learning": "深度学习基础",
    "neural_network": "神经网络",
    "backpropagation": "反向传播",
    "convolution": "卷积网络",
}


class LearningPlanModule:
    """从已完成的诊断会话生成前端学习任务。"""

    DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "learning_plan" / "plans.json"

    def __init__(self, sessions: DiagnosticSessionStore, agent: LearningPlanAgent | None = None, path: str | Path | None = None, memory: "MemoryModule | None" = None) -> None:
        """保存诊断会话存储，并允许注入自定义计划生成代理。"""
        self.sessions = sessions
        self.agent = agent or LearningPlanAgent()
        target = path or self.DEFAULT_PATH
        self.reader = common_api.json_storage.JsonContentReader(target)
        self.store = common_api.json_storage.JsonStore()
        self.memory = memory

    def get_saved(self, *, book_id: str, diagnostic_id: str | None = None) -> dict[str, Any] | None:
        payload = self.reader.read(allow_missing=True, allow_empty=False)
        if payload == {}:
            return None
        if not isinstance(payload, dict):
            raise common_api.errors.StorageReadError("learning plan resource must be a JSON object")
        candidates = [item for item in payload.values() if isinstance(item, dict) and item.get("bookId") == book_id and item.get("status") != "completed"]
        if diagnostic_id:
            candidates = [item for item in candidates if item.get("diagnosticId") == diagnostic_id]
        if not candidates:
            return None
        return candidates[-1].get("plan")

    def create_task_plan(
        self,
        *,
        book_id: str,
        task: dict[str, Any],
        goal: str,
        goal_level: str,
        advice: list[str] | None = None,
        resources: list[dict[str, Any]] | None = None,
        plan_key: str | None = None,
        diagnostic_id: str = "",
    ) -> dict[str, Any]:
        """Create/extend a plan and persist it through the shared plan store.

        Both diagnostic-generated tasks and material-QA tasks use this entry
        point so task shape and local persistence stay consistent.
        """
        existing = self.get_saved(book_id=book_id, diagnostic_id=diagnostic_id or None)
        if existing is None:
            plan = {
                "book": self._book(book_id),
                "goal": goal,
                "goalLevel": goal_level,
                "tasks": [task],
                "advice": advice or [],
                "resources": resources or [],
            }
        else:
            plan = dict(existing)
            plan["tasks"] = [*existing.get("tasks", []), task]
            plan["resources"] = self._merge_resources(existing.get("resources", []), resources or [])
            plan["advice"] = list(dict.fromkeys([*existing.get("advice", []), *(advice or [])]))
        key = plan_key or f"{book_id}:{diagnostic_id or 'material'}:{task['id']}"
        self.persist_plan(
            book_id=book_id,
            diagnostic_id=diagnostic_id,
            plan=plan,
            plan_key=key,
        )
        return plan

    def persist_plan(
        self,
        *,
        book_id: str,
        diagnostic_id: str,
        plan: dict[str, Any],
        plan_key: str,
    ) -> dict[str, Any]:
        """Persist any plan shape through the single local storage gateway."""
        self.store.save(
            path=self.reader.path,
            content={"bookId": book_id, "diagnosticId": diagnostic_id, "plan": plan},
            mode="upsert",
            key_path=[plan_key],
        )
        return plan

    def complete_task(self, *, user_id: str, task_id: str, plan_id: str = "", book_id: str = "") -> dict[str, Any]:
        """Complete a server-owned task, update its plan, and update memory."""
        payload = self.reader.read(allow_missing=True, allow_empty=False)
        if not isinstance(payload, dict):
            raise common_api.errors.StorageReadError("learning plan resource must be a JSON object")
        match_key = None
        match_record = None
        match_task = None
        for key, record in payload.items():
            if not isinstance(record, dict) or (book_id and record.get("bookId") != book_id):
                continue
            if plan_id and key != plan_id and record.get("planId") != plan_id and record.get("diagnosticId") != plan_id:
                continue
            plan = record.get("plan")
            if not isinstance(plan, dict):
                continue
            task = next((item for item in plan.get("tasks", []) if isinstance(item, dict) and item.get("id") == task_id), None)
            if task is not None:
                match_key, match_record, match_task = key, record, task
                break
        if match_record is None or match_task is None:
            raise ValidationAppError("learning task not found", details={"task_id": task_id})

        plan = dict(match_record["plan"])
        tasks = [dict(item) for item in plan.get("tasks", [])]
        was_completed = bool(match_task.get("status") == "completed")
        for task in tasks:
            if task.get("id") == task_id:
                task["status"] = "completed"
        all_completed = bool(tasks) and all(item.get("status") == "completed" for item in tasks)
        plan["tasks"] = tasks
        if all_completed:
            plan["status"] = "completed"
            match_record = {**match_record, "status": "completed"}
        else:
            match_record = {**match_record, "plan": plan}
        match_record["plan"] = plan
        self.store.save(path=self.reader.path, content=match_record, mode="upsert", key_path=[match_key])

        memories = []
        if self.memory and match_record.get("bookId") and not was_completed:
            learning_domain = {"ml": "ml-001", "dl": "dl-001"}.get(
                str(match_record["bookId"]), str(match_record["bookId"])
            )
            memories = self.memory.ingest_task_completion(
                user_id=user_id,
                learning_domain=learning_domain,
                task_id=task_id,
                knowledge_point_ids=list(
                    match_task.get("knowledgePointIds")
                    or match_task.get("knowledge_point_ids")
                    or []
                ),
            )
        return {
            "plan": plan,
            "planCompleted": all_completed,
            "memoryUpdated": bool(memories),
            "bookId": match_record.get("bookId", ""),
            "planId": match_key,
            "knowledgePointIds": list(
                match_task.get("knowledgePointIds")
                or match_task.get("knowledge_point_ids")
                or []
            ),
            "alreadyCompleted": was_completed,
        }

    def generate(self, *, diagnostic_id: str, book_id: str, goal: str) -> dict[str, Any]:
        """校验输入后，生成任务、学习建议及相关资源。"""
        # 诊断会话是生成计划的事实来源，先按编号读取会话。
        session = self.sessions.get(diagnostic_id)
        # 兼容前端教材编号和后端题库编号，防止跨教材生成计划。
        expected_book_id = BOOK_TO_QUESTION_BANK.get(book_id, book_id)
        if session.book_id != expected_book_id:
            raise ValidationAppError(
                "diagnostic session does not belong to the requested book",
                details={"diagnostic_id": diagnostic_id, "book_id": book_id},
            )
        # 只有完成校准且存在结果时，诊断数据才足以支撑学习计划。
        if session.status != "completed" or session.result is None:
            raise WorkflowStateError(
                "learning plan requires a completed calibration",
                details={"diagnostic_id": diagnostic_id, "session_status": session.status},
            )
        
        #从已完成的诊断会话读取用户答题结果
        results = session.result.get("results", [])
        # 诊断按知识点统计，计划按能力聚合；知识点和章节作为任务证据保留。
        planning_units = self._build_planning_units(session.questions, session.result.get("answer_records", []), results)
        #按照能力掌握排序
        ordered_results = sorted(planning_units, key=self._status_rank)
        tasks = [
            self._build_task(diagnostic_id, item, index, goal)
            for index, item in enumerate(ordered_results)
        ]
        plan = self.agent.build({
            "diagnostic_id": diagnostic_id,
            "book": self._book(book_id),
            "goal": goal,
            "goal_level": self._goal_level(results),
            "questions": session.questions, 
            "answers": session.answers,
            "correct_answers": session.correct_answers,
            "answer_records": session.result.get("answer_records", []),
            "diagnosis_results": results,
            "tasks": tasks,
        })
        self.persist_plan(
            book_id=book_id,
            diagnostic_id=diagnostic_id,
            plan=plan,
            plan_key=f"{book_id}:{diagnostic_id}",
        )
        return plan

    def create_from_material(
        self,
        *,
        book_id: str,
        title: str,
        goal: str,
        description: str,
        minutes: int,
        expected_completion_date: str,
        resources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """根据资料问答来源创建并持久化一个自定义学习任务。"""

        task_id = f"material-{book_id}-{uuid4().hex[:10]}"
        knowledge_point_ids = self._knowledge_points_for_resources(resources)
        task = {
            "id": task_id,
            "title": title,
            "type": "资料问答",
            "minutes": minutes,
            "status": "todo",
            "reason": "基于资料问答来源创建",
            "description": description or f"围绕“{goal}”复习资料并完成知识点整理。",
            "learningGoal": goal,
            "expectedCompletionDate": expected_completion_date,
            "knowledgePointIds": knowledge_point_ids,
        }

        return self.create_task_plan(
            book_id=book_id,
            task=task,
            goal=goal,
            goal_level="自定义学习目标",
            advice=["建议先阅读关联教材，再回到资料问答中进行复习和追问。"],
            resources=resources,
            plan_key=f"{book_id}:material:{task_id}",
        )

    @staticmethod
    def _knowledge_points_for_resources(resources: list[dict[str, Any]]) -> list[str]:
        """Resolve source content units to knowledge points on the backend."""
        content_unit_ids = {
            str(item.get("contentUnitId") or item.get("content_unit_id"))
            for item in resources
            if item.get("contentUnitId") or item.get("content_unit_id")
        }
        if not content_unit_ids:
            return ["unknown"]
        data_dir = Path(__file__).resolve().parents[2] / "data" / "02-内容与数据" / "data"
        edge_path = data_dir / "content_unit_knowledge_edges.csv"
        if not edge_path.exists():
            return ["unknown"]
        with edge_path.open(encoding="utf-8-sig", newline="") as handle:
            points = {
                row.get("knowledge_point_id", "")
                for row in csv.DictReader(handle)
                if row.get("content_unit_id") in content_unit_ids and row.get("knowledge_point_id")
            }
        return sorted(points) or ["unknown"]

    @staticmethod
    def _merge_resources(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for resource in [*existing, *incoming]:
            key = str(resource.get("title") or resource.get("id") or len(merged))
            merged[key] = resource
        return list(merged.values())

    @staticmethod
    def _book(book_id: str) -> dict[str, str]:
        """把教材编号转换为前端需要的教材展示信息。"""
        books = {
            "ml": {"id": "ml", "title": "《机器学习》", "shortTitle": "机器学习"},
            "dl": {"id": "dl", "title": "《深度学习》", "shortTitle": "深度学习"},
        }
        return books.get(book_id, {"id": book_id, "title": book_id, "shortTitle": book_id})

    @staticmethod
    def _goal_level(results: list[dict[str, Any]]) -> str:
        """根据所有知识点的诊断状态推断用户当前目标层级。"""
        statuses = [str(item.get("calibrated_status") or item.get("ai_status") or "") for item in results]
        if not statuses:
            return ""
        if all(status == STATUSES[-1] for status in statuses):
            return "能够迁移到项目实践"
        if any(status == STATUSES[1] for status in statuses):
            return "了解核心概念"
        return "能够独立完成基础练习"

    @staticmethod
    def _effective_status(result: dict[str, Any]) -> str:
        """优先使用校准状态，其次使用模型状态，最后回退到最低状态。"""
        return result.get("calibrated_status") or result.get("ai_status") or result.get("status") or STATUSES[0]

    def _status_rank(self, result: dict[str, Any]) -> int:
        """返回诊断状态在预设状态序列中的位置，用于任务排序。"""
        status = self._effective_status(result)
        return STATUSES.index(status) if status in STATUSES else 0
    

    def _build_planning_units(
        self,
        questions: list[dict[str, Any]],
        answer_records: list[dict[str, Any]],
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """把知识点诊断证据聚合成能力级计划单元。"""
        result_by_point = {str(item.get("knowledge_point_id")): item for item in results}
        records_by_question = {str(item.get("question_id")): item for item in answer_records}
        #记录能力
        units: dict[str, dict[str, Any]] = {}
        for question in questions:
            question_id = str(question.get("id", ""))
            #获取题目所属的能力
            ability_ids = [str(item) for item in question.get("ability_ids", []) if item]
            if not ability_ids:
                ability_ids = [f"knowledge:{question.get('tag', 'unknown')}" ]
            #获取题目所属的作答记录
            record = records_by_question.get(question_id, {})
            #获取题目所属的知识点
            knowledge_ids = [str(item) for item in question.get("knowledge_point_ids", []) if item]
            if not knowledge_ids and question.get("tag"):
                knowledge_ids = [str(question["tag"])]
            #按能力聚合
            for ability_id in ability_ids:
                unit = units.setdefault(
                    ability_id,
                    {
                        "ability_id": ability_id,
                        "knowledge_point_ids": [],
                        "chapter_ids": [],
                        "question_ids": [],
                        "correct": 0,
                        "total": 0,
                        "statuses": [], #关联知识点的掌握状态
                    },
                )
                unit["question_ids"].append(question_id)
                unit["correct"] += int(bool(record.get("is_correct")))
                unit["total"] += 1
                unit["knowledge_point_ids"] = sorted(set(unit["knowledge_point_ids"]) | set(knowledge_ids))
                chapter_id = str(question.get("chapter_id", ""))
                if chapter_id:
                    unit["chapter_ids"] = sorted(set(unit["chapter_ids"]) | {chapter_id})
                unit["statuses"].extend(
                    self._effective_status(result_by_point[item])
                    for item in knowledge_ids
                    if item in result_by_point
                )
        #目前是采用短板规则，即直接返回最弱
        for unit in units.values():
            unit["status"] = min(unit["statuses"], key=lambda value: STATUSES.index(value)) if unit["statuses"] else STATUSES[0]
            unit.pop("statuses", None)
        return list(units.values())
    
    #生成任务字段
    def _build_task(self, diagnostic_id: str, result: dict[str, Any], index: int, goal: str) -> dict[str, Any]:
        """把一个能力级计划单元转换为任务，知识点是任务的支撑范围。"""
        ability_id = str(result.get("ability_id", "ability"))
        #把内部能力 ID 转换为用户可读名称
        name = {"math": "数学能力", "algorithm": "算法能力", "programming": "编程能力", "conceptual": "概念理解能力"}.get(ability_id, ability_id.replace("_", " "))
        status = str(result.get("status", STATUSES[0]))
        correct = int(result.get("correct", 0))
        total = int(result.get("total", 0))
        minutes = self._minutes_for(status)
        return {
            "id": f"{diagnostic_id}-ability-{ability_id}",
            "ability_id": ability_id,
            "knowledgePointIds": result.get("knowledge_point_ids", []),
            "chapterIds": result.get("chapter_ids", []),
            "questionIds": result.get("question_ids", []),
            "title": f"提升{name}",
            "type": "能力强化" if index == 0 else "能力练习",
            "minutes": minutes,
            "status": "in_progress" if index == 0 else "todo",
            "reason": f"诊断结果为“{status}”，答对 {correct}/{total} 题",
            "description": f"围绕“{goal}”提升{name}，复习关联知识点并完成迁移练习。",
        }

    @staticmethod
    def _minutes_for(status: str) -> int:
        """根据知识点掌握状态估算本次学习任务所需分钟数。"""
        if status in {STATUSES[0], STATUSES[1]}:
            return 25
        if status == STATUSES[2]:
            return 20
        return 15
