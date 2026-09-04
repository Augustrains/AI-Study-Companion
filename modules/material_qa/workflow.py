"""Workflow orchestration for material question answering."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from .agent import MaterialQaAgent, MaterialQaQueryRewriter
from .models import AnswerMode, MaterialQaAnswer, MaterialQaConversation, ResponseQuality
from .repository import MaterialQaMessageStore
from .services import (
    MaterialQaActivityRecorder,
    MaterialQaRetriever,
    MaterialQaService,
    QdrantMaterialRetriever,
)
from .socratic import MaterialQaResponseClassifier, SocraticEngine


class MaterialQaWorkflow:
    """Coordinate conversation state, retrieval, and one Agent invocation."""

    def __init__(
        self,
        agent: MaterialQaAgent | None = None,
        retriever: MaterialQaRetriever | None = None,
        activity_recorder: MaterialQaActivityRecorder | None = None,
        qa_service: MaterialQaService | None = None,
        message_store: MaterialQaMessageStore | None = None,
        query_rewriter: MaterialQaQueryRewriter | None = None,
        response_classifier: MaterialQaResponseClassifier | None = None,
    ) -> None:
        self.agent = agent or MaterialQaAgent()
        self.query_rewriter = query_rewriter or MaterialQaQueryRewriter(self.agent.llm_client)
        self.response_classifier = response_classifier or MaterialQaResponseClassifier(self.agent.llm_client)
        self.retriever = retriever or QdrantMaterialRetriever(
            documents={},
            qdrant_path=Path("data/qdrant"),
        )
        self.qa_service = qa_service or MaterialQaService(
            message_store=message_store,
            activity_recorder=activity_recorder,
        )

    def start(self) -> None:
        """预热检索资源，不在此阶段创建或重建索引。"""

        start = getattr(self.retriever, "start", None)
        if callable(start):
            start()

    def close(self) -> None:
        close = getattr(self.retriever, "close", None)
        if callable(close):
            close()

    def create_conversation(
        self,
        *,
        book_id: str,
        user_id: str,
        reset_context: bool = False,
    ) -> MaterialQaConversation:
        return self.qa_service.create_conversation(
            book_id=book_id,
            user_id=user_id,
            reset_context=reset_context,
        )

    def finish_learning_task(self, *, user_id: str, book_id: str, learning_task_id: str) -> None:
        self.qa_service.finish_learning_task(
            user_id=user_id,
            book_id=book_id,
            learning_task_id=learning_task_id,
        )

    # 资料问答的一条完整处理流程：读取历史 → 检索资料 → 调用大模型 → 保存问答 → 返回结果。
    def ask(
        self,
        *,
        conversation_id: str,
        user_id: str,
        book_id: str,
        question: str,
        source_ids: list[str] | None = None,    # 可选，限制只从指定资料来源中检索。
        allow_general_fallback: bool = False,   # - 资料没找到答案时，是否允许模型使用通用知识回答。
        answer_mode: AnswerMode = "direct",
        learning_task_id: str | None = None,
    ) -> MaterialQaAnswer:
        # 读取历史对话
        history = self.qa_service.begin_question(
            user_id=user_id,
            book_id=book_id,
        )
        # 恢复已有的苏格拉底任务，包括任务问题，最新人机回答，最新状态，最新状态停留时间，一直使用原问题进行向量检索
        task = None
        if answer_mode == "socratic" and learning_task_id:
            task = self.qa_service.message_store.get_learning_task(
                user_id=user_id,
                book_id=book_id,
                learning_task_id=learning_task_id,
            )
        # 引导模式
        if answer_mode == "socratic":
            learning_task_id = learning_task_id or f"task-{uuid4().hex[:12]}"
            root_question = task.root_question if task else question
            # A Socratic reply is often a fragment rather than a searchable question.
            # Keep retrieval anchored to the original task to prevent topic drift.
            standalone_question = root_question
        # 普通问答不需要学习任务，所以清空：
        else:
            root_question = ""
            learning_task_id = None
            standalone_question = self.query_rewriter.rewrite(
                history=history,
                question=question,
            )
        # 从 Qdrant 检索教材
        retrieval = self.retriever.retrieve(
            book_id=book_id,
            question=standalone_question,
            source_ids=source_ids,
        )
        # 初始化引导结果,普通直接回答不会使用这些数据。
        response_quality: ResponseQuality | None = None
        socratic_state = None
        socratic_directive = ""
        socratic_completed = False
        if answer_mode == "socratic":
            # 创建苏格拉底状态机
            engine = SocraticEngine(
                state=task.state if task else "probe",
                turns_in_state=task.turns_in_state if task else 0,
            )
            # 利用LLM判断学生本轮回答
            if task and task.last_assistant_message:
                # Classify and transition BEFORE generating this turn. This avoids
                # the one-turn lag found in implementations that save state afterward.
                response_quality = self.response_classifier.classify(
                    root_question=root_question,
                    tutor_message=task.last_assistant_message,
                    learner_message=question,
                    material_context=retrieval.text,
                )
                # 上一轮已经是迁移验证状态 confirm 且学生回答正确 correct认为这道学习任务完成。
                socratic_completed = task.state == "confirm" and response_quality == "correct"
                # 状态转移，获得本轮教学指令，未完成时，状态 yourself转换 Brigade Energizing 指令。
                if not socratic_completed:
                    engine.transition(response_quality)
            socratic_state = engine.state
            socratic_directive = (
                "学习者已经通过迁移验证。简要总结其已经掌握的思路，指出一个可继续深化的方向，"
                "并明确说明本轮引导已经完成。不要再提出必须回答的问题。"
                if socratic_completed
                else engine.directive
            )
        # 生成回答
        output = self.agent.generate(
            self.qa_service.agent_input(
                history=history,
                question=question,
                retrieval=retrieval,
                allow_general_fallback=allow_general_fallback,
                answer_mode=answer_mode,
                learning_task_id=learning_task_id,
                socratic_state=socratic_state,
                socratic_directive=socratic_directive,
                root_question=root_question,
            )
        )
        if answer_mode == "socratic":
            output = type(output)(
                answer=output.answer,
                refused=output.refused,
                citations=output.citations,
                related_knowledge_points=output.related_knowledge_points,
                recommended_action=output.recommended_action,
                answered_by_general_model=output.answered_by_general_model,
                answer_mode=answer_mode,
                learning_task_id=learning_task_id,
                socratic_state=socratic_state,
                response_quality=response_quality,
                socratic_completed=socratic_completed,
            )
        # 保存本轮问答
        return self.qa_service.complete_question(
            conversation_id=conversation_id,
            user_id=user_id,
            book_id=book_id,
            question=question,
            output=output,
        )
