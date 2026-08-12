"""诊断模块的 LangGraph 流程、答案评估和会话门面。"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable, TypedDict
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from modules.common.errors import ResourceNotFoundError, ValidationAppError
from modules.memory.module import MemoryModule
from modules.learning_record.module import LearningRecordModule

from .agent import DiagnosticAgent, DiagnosticAnalysisInput
from .field_rules import parse_answer_fields, parse_review_fields, parse_start_fields
from .models import DiagnosticSession, DiagnosisResult, KnowledgePointResult, Question, QuestionOption, STATUSES
from .question_bank import QuestionBank
from .result_builder import DiagnosisResultBuilder


class DiagnosisState(TypedDict, total=False):
    """LangGraph 在诊断各节点之间传递的共享状态。"""

    workflow_run_id: str
    diagnosis_id: str
    diagnostic_session_id: str
    user_id: str
    book_id: str
    learning_goal: str
    mastered_skill_ids: list[str]
    questions: list[dict[str, Any]]
    correct_answers: dict[str, str]
    answers: dict[str, str]
    draft_results: list[dict[str, Any]]
    answer_records: list[dict[str, Any]]
    review_action: str
    calibrations: dict[str, str]
    status: str


class AssessmentService:
    """根据题目和答案计算知识点表现。"""
    
    #实际的评估函数
    def evaluate(self, questions: Iterable[Question], answers: dict[str, str], correct_answers: dict[str, str]) -> tuple[list[KnowledgePointResult], list[dict[str, str | bool]]]:
        """计算每个知识点的正确数、总题数和能力状态。"""
        grouped: dict[str, list[tuple[Question, bool]]] = defaultdict(list)
        records: list[dict[str, str | bool]] = []
        for question in questions:
            # 获取用户对当前题目的答案
            submitted = answers.get(question.id, "")
            submitted_id = self._to_option_id(question, submitted)
            # 与标准答案进行比较
            expected = correct_answers.get(question.id, "")
            is_correct = self._normalize(submitted_id) == self._normalize(expected)
            # 按知识点分组
            grouped[question.tag].append((question, is_correct))
            # 保存每道题的作答记录
            records.append({"question_id": question.id, "submitted_answer": submitted_id, "is_correct": is_correct, "source": question.source})
        results = []
        # 针对每个知识点统计诊断结果
        for knowledge_point_id, items in grouped.items():
            correct = sum(is_correct for _, is_correct in items)
            total = len(items)
            results.append(KnowledgePointResult
            (knowledge_point_id=knowledge_point_id, 
            ai_status=self._status_for(correct / total), 
            correct=correct, total=total))
        return results, records

    @staticmethod
    def _to_option_id(question: Question, answer: str) -> str:
        if answer in {option.id for option in question.options}:
            return answer
        normalized = AssessmentService._normalize(answer)
        return next((option.id for option in question.options if AssessmentService._normalize(option.text) == normalized), answer)

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


class DiagnosticSessionStore:
    """保存运行中的诊断会话；当前实现使用内存字典。"""
    """保存运行中的诊断会话。"""

    def __init__(self) -> None:
        # 临时内存存储，服务重启后会丢失；后续应替换为数据库或 Redis 等持久化存储。
        self._sessions: dict[str, DiagnosticSession] = {}

    def save(self, session: DiagnosticSession) -> None:
        self._sessions[session.id] = session

    def get(self, session_id: str) -> DiagnosticSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise ResourceNotFoundError("diagnostic session not found: %s" % session_id, details={"resource": "diagnostic_session", "session_id": session_id}) from exc


def build_diagnosis_graph(question_bank: QuestionBank, assessment_service: AssessmentService, checkpointer: Any):
    """组装诊断 LangGraph：出题、答题、评估、解释和审核。"""
    def load_questions(state: DiagnosisState) -> dict[str, Any]:
        """加载题库并转换成前端可展示的题目结构。"""
        question_set = question_bank.get_questions(
            state["book_id"],
            state.get("learning_goal", ""),
            mastered_skill_ids=state.get("mastered_skill_ids", []),
        )
        questions = [
            {"id": q.id, "title": q.title, "tag": q.tag, "book_id": q.book_id, "chapter_id": q.chapter_id, "section_ids": q.section_ids, "knowledge_point_ids": q.knowledge_point_ids, "ability_ids": q.ability_ids, "difficulty": q.difficulty, "source": q.source, "options": [{"id": o.id, "text": o.text} for o in q.options]}
            for q in question_set.questions
        ]
        return {
            "questions": questions,
            "correct_answers": question_set.correct_answers,
            "status": "waiting_for_answers",
        }

    def wait_for_answers(state: DiagnosisState) -> dict[str, Any]:
        """通过 LangGraph interrupt 暂停，等待用户提交答案。"""
        answers = interrupt({"type": "answer_request", "diagnosis_id": state["diagnosis_id"], "questions": state["questions"]})
        if not isinstance(answers, dict):
            raise ValueError("提交答案必须是题目 ID 到答案的字典")
        return {"answers": answers, "status": "evaluating"}

    def evaluate_answers(state: DiagnosisState) -> dict[str, Any]:
        """调用评估服务，生成知识点结果和答题记录。"""
        questions = [
            Question(
                id=item["id"],
                title=item["title"],
                tag=item["tag"],
                book_id=item.get("book_id", ""),
                chapter_id=item.get("chapter_id", ""),
                section_ids=item.get("section_ids", []),
                knowledge_point_ids=item.get("knowledge_point_ids", []),
                ability_ids=item.get("ability_ids", []),
                difficulty=item.get("difficulty", ""),
                options=[QuestionOption(**option) for option in item["options"]],
                source=item.get("source", ""),
            )
            for item in state["questions"]
        ]
        results, records = assessment_service.evaluate(
            questions,
            state["answers"],
            state["correct_answers"],
        )
        return {"draft_results": [result.__dict__.copy() for result in results], "answer_records": records}

    def wait_for_review(state: DiagnosisState) -> dict[str, Any]:
        """暂停等待用户批准、编辑或拒绝诊断结果。"""
        decision = interrupt({"type": "diagnosis_review", "diagnosis_id": state["diagnosis_id"], "draft_results": state["draft_results"], "allowed_actions": ["approve", "edit", "reject"]})
        if not isinstance(decision, dict):
            raise ValueError("确认结果必须包含 action 字段")
        action = decision.get("action")
        if action not in {"approve", "edit", "reject"}:
            raise ValueError("不支持的确认操作: %s" % action)
        calibrations = decision.get("calibrations", {})
        if not isinstance(calibrations, dict):
            raise ValueError("calibrations 必须是知识点到状态的字典")
        if action == "edit":
            known = {item["knowledge_point_id"] for item in state["draft_results"]}
            unknown = set(calibrations) - known
            if unknown:
                raise ValueError("校准包含未知知识点: %s" % sorted(unknown))
            invalid = {key: value for key, value in calibrations.items() if value not in STATUSES[1:]}
            if invalid:
                raise ValueError("包含不支持的校准状态: %s" % invalid)
        return {"review_action": action, "calibrations": calibrations if action == "edit" else {}, "status": "rejected" if action == "reject" else "approved"}

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
    builder.add_conditional_edges("wait_for_review", lambda state: "finish_rejected" if state["review_action"] == "reject" else "commit", {"commit": "commit", "finish_rejected": "finish_rejected"})
    builder.add_edge("commit", END)
    builder.add_edge("finish_rejected", END)
    return builder.compile(checkpointer=checkpointer)


class DiagnosisWorkflow:
    """封装 LangGraph 的启动、答题提交和结果审核。"""

    def __init__(self, question_bank: QuestionBank, session_store: DiagnosticSessionStore, assessment_service: AssessmentService, diagnostic_agent: DiagnosticAgent, memory: MemoryModule | None = None, learning_record: LearningRecordModule | None = None, checkpointer: Any | None = None) -> None:
        self.session_store = session_store
        self.question_bank = question_bank
        self.memory = memory
        self.learning_record = learning_record
        self.diagnostic_agent = diagnostic_agent
        self.checkpointer = checkpointer or InMemorySaver()
        self.graph = build_diagnosis_graph(question_bank, assessment_service, self.checkpointer)

    @staticmethod
    def _config(diagnosis_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": diagnosis_id}}

    def start_diagnosis(self, *, user_id: str, book_id: str, learning_goal: str) -> dict[str, Any]:
        """统一编排诊断启动：校验、选题、建会话并启动状态图。"""
        values = parse_start_fields(user_id, book_id, learning_goal)
        
        session = DiagnosticSession(
            id=f"diag_{uuid4().hex[:10]}",
            user_id=values["user_id"],
            book_id=values["book_id"],
            learning_goal=values["learning_goal"],
        )
        self.start(session)
        return {"diagnostic_id": session.id, "questions": session.questions}

    def submit_answer(self, diagnosis_id: str, question_id: str, answer: str, skipped: bool = False) -> dict[str, Any]:
        """统一保存单题答案。"""
        values = parse_answer_fields(diagnosis_id, question_id, answer)
        session = self.session_store.get(values["diagnosis_id"])
        question = next((item for item in session.questions if item["id"] == values["question_id"]), None)
        if question is None:
            raise ResourceNotFoundError("unknown question: %s" % values["question_id"], details={"resource": "question", "question_id": values["question_id"]})
        if not skipped and values["answer"] not in {option["id"] for option in question["options"]}:
            raise ValidationAppError("invalid answer for question: %s" % values["question_id"], details={"field": "answer", "question_id": values["question_id"]})
        session.answers[values["question_id"]] = "" if skipped else values["answer"]
        self.session_store.save(session)
        return {"diagnostic_id": values["diagnosis_id"], "question_id": values["question_id"], "saved": True}

    async def finish_diagnosis(self, diagnosis_id: str) -> dict[str, Any]:
        """统一完成答题、评估知识点并生成待校准摘要。"""
        session = self.session_store.get(diagnosis_id)
        draft = await self.submit_async(diagnosis_id, session.answers)
        results = draft.get("draft_results", [])
        question_results = DiagnosisResultBuilder.question_results(session)
        total = len(question_results)
        correct = sum(bool(item["is_correct"]) for item in question_results)
        answered = sum(not item["skipped"] for item in question_results)
        confidence = "high" if answered >= len(session.questions) else "medium"
        statuses = [item.get("ai_status") for item in results]
        level = max(statuses, key=lambda value: STATUSES.index(value)) if statuses else STATUSES[0]
        accuracy = round(correct / total * 100) if total else 0
        analysis = await self.diagnostic_agent.analyze_performance(
            DiagnosticAnalysisInput(
                diagnosis_id=diagnosis_id,
                learning_goal=session.learning_goal,
                total_questions=total,
                answered_questions=answered,
                skipped_questions=total - answered,
                correct_questions=correct,
                accuracy=float(accuracy),
                level=level,
                confidence=confidence,
                knowledge_point_results=results,
                question_results=question_results,
            )
        )
        session.status = "awaiting_review"
        self.session_store.save(session)
        return DiagnosisResultBuilder.summary(session, results, analysis)

    def confirm_diagnosis(self, diagnosis_id: str, *, calibration: str = "same", reason: str = "") -> DiagnosisResult | None:
        """统一确认诊断、保存最终结果并更新学习记录和长期记忆。"""
        values = parse_review_fields(diagnosis_id, calibration, reason)
        state = self.graph.get_state(self._config(values["diagnosis_id"])).values
        results = state.get("draft_results", [])
        calibrations: dict[str, str] = {}
        if values["calibration"] != "same":
            delta = -1 if values["calibration"] == "lower" else 1
            for item in results:
                statuses = STATUSES[1:]
                calibrations[item["knowledge_point_id"]] = statuses[max(0, min(len(statuses) - 1, statuses.index(item["ai_status"]) + delta))]
        diagnosis = self.review(values["diagnosis_id"], action="edit" if calibrations else "approve", calibrations=calibrations)
        if diagnosis is None:
            return None
        if self.learning_record is not None:
            self.learning_record.record_completed_diagnosis(diagnosis)
        if self.memory is not None:
            self.memory.ingest_diagnosis(diagnosis)
        return diagnosis

    def start(self, session: DiagnosticSession) -> dict[str, Any]:
        """创建会话并启动图，返回题目等待状态。"""
        mastered = self.memory.mastered_skill_ids(session.user_id, session.book_id) if self.memory else set()
        self.session_store.save(session)
        result = self.graph.invoke({"workflow_run_id": session.id, "diagnosis_id": session.id, "diagnostic_session_id": session.id, "user_id": session.user_id, "book_id": session.book_id, "learning_goal": session.learning_goal, "mastered_skill_ids": sorted(mastered), "status": "started"}, config=self._config(session.id))
        state = self.graph.get_state(self._config(session.id)).values
        session.questions = state.get("questions", [])
        session.correct_answers = state.get("correct_answers", {})
        self.session_store.save(session)
        return result["__interrupt__"][0].value


    async def submit_async(self, diagnosis_id: str, answers: dict[str, str]) -> dict[str, Any]:
        """异步恢复图执行"""
        session = self.session_store.get(diagnosis_id)
        session.answers = dict(answers)
        result = await self.graph.ainvoke(Command(resume=answers), config=self._config(diagnosis_id))
        session.status = "awaiting_review"
        self.session_store.save(session)
        return result["__interrupt__"][0].value

    def submit(self, diagnosis_id: str, answers: dict[str, str]) -> dict[str, Any]:
        """Synchronous compatibility wrapper for scripts and legacy callers."""
        session = self.session_store.get(diagnosis_id)
        session.answers = dict(answers)
        result = self.graph.invoke(Command(resume=answers), config=self._config(diagnosis_id))
        session.status = "awaiting_review"
        self.session_store.save(session)
        return result["__interrupt__"][0].value

    def review(self, diagnosis_id: str, *, action: str = "approve", calibrations: dict[str, str] | None = None) -> DiagnosisResult | None:
        """恢复图执行并完成批准、编辑或拒绝操作。"""
        result = self.graph.invoke(Command(resume={"action": action, "calibrations": calibrations or {}}), config=self._config(diagnosis_id))
        if result["status"] == "rejected":
            session = self.session_store.get(diagnosis_id)
            session.status = "rejected"
            self.session_store.save(session)
            return None
        state = self.graph.get_state(self._config(diagnosis_id)).values
        session = self.session_store.get(diagnosis_id)
        diagnosis = DiagnosisResultBuilder.final(session, state["draft_results"], state.get("calibrations", {}))
        session.status = "completed"
        session.result = {"results": [item.__dict__.copy() for item in diagnosis.results], "answer_records": diagnosis.answer_records}
        self.session_store.save(session)
        return diagnosis

    @staticmethod
    def _public_question(question: Question) -> dict[str, Any]:
        return {
            "id": question.id,
            "title": question.title,
            "tag": question.tag,
            "book_id": question.book_id,
            "chapter_id": question.chapter_id,
            "section_ids": question.section_ids,
            "knowledge_point_ids": question.knowledge_point_ids,
            "ability_ids": question.ability_ids,
            "difficulty": question.difficulty,
            "options": [{"id": option.id, "text": option.text} for option in question.options],
            "source": question.source,
        }
