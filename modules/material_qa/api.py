from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .schemas import (
    AskMaterialQuestionRequest,
    AskMaterialQuestionResponse,
    CreateMaterialQaConversationRequest,
    CreateMaterialQaConversationResponse,
    FinishMaterialQaLearningTaskRequest,
)
from .models import MaterialQaAnswer, MaterialQaConversation
from .workflow import MaterialQaWorkflow


def build_router(workflow: MaterialQaWorkflow) -> APIRouter:
    router = APIRouter(tags=["material-qa"])

    def conversation_response(conversation: MaterialQaConversation) -> dict[str, Any]:
        task = conversation.active_learning_task
        return {
            "conversation_id": conversation.conversation_id,
            "book_id": conversation.book_id,
            "user_id": conversation.user_id,
            "created_at": conversation.created_at,
            "status": "active",
            "answer_mode": "socratic" if task else "direct",
            "learning_task_id": task.learning_task_id if task else None,
            "socratic_state": task.state if task else None,
        }

    def answer_response(answer: MaterialQaAnswer, request_id: str) -> dict[str, Any]:
        return {
            "answer": answer.answer,
            "refused": answer.refused,
            "citations": answer.citations,
            "related_knowledge_points": answer.related_knowledge_points,
            "recommended_action": answer.recommended_action,
            "conversation_id": answer.conversation_id,
            "request_id": request_id,
            "answered_by_general_model": answer.answered_by_general_model,
            "answer_mode": answer.answer_mode,
            "learning_task_id": answer.learning_task_id,
            "socratic_state": answer.socratic_state,
            "response_quality": answer.response_quality,
            "socratic_completed": answer.socratic_completed,
        }

    @router.post("/api/rag/conversations", response_model=CreateMaterialQaConversationResponse)
    def create_conversation(payload: CreateMaterialQaConversationRequest) -> dict[str, Any]:
        return conversation_response(
            workflow.create_conversation(
                book_id=payload.book_id,
                user_id=payload.user_id,
                reset_context=payload.reset_context,
            )
        )

    @router.post("/api/rag/conversations/{conversation_id}/messages", response_model=AskMaterialQuestionResponse)
    def ask_in_conversation(conversation_id: str, payload: AskMaterialQuestionRequest) -> dict[str, Any]:
        result = workflow.ask(
            conversation_id=conversation_id,
            user_id=payload.user_id,
            book_id=payload.book_id,
            question=payload.question,
            source_ids=payload.source_ids,
            allow_general_fallback=payload.allow_general_fallback,
            answer_mode=payload.answer_mode,
            learning_task_id=payload.learning_task_id,
        )
        return answer_response(result, f"req-{conversation_id}")

    @router.post("/api/rag/ask", response_model=AskMaterialQuestionResponse)
    def ask_material_question(payload: AskMaterialQuestionRequest) -> dict[str, Any]:
        conversation_id = payload.conversation_id
        if conversation_id is None:
            conversation_id = workflow.create_conversation(book_id=payload.book_id, user_id=payload.user_id).conversation_id
        result = workflow.ask(
            conversation_id=conversation_id,
            user_id=payload.user_id,
            book_id=payload.book_id,
            question=payload.question,
            source_ids=payload.source_ids,
            allow_general_fallback=payload.allow_general_fallback,
            answer_mode=payload.answer_mode,
            learning_task_id=payload.learning_task_id,
        )
        return answer_response(result, f"req-{conversation_id}")

    @router.post("/api/rag/learning-tasks/{learning_task_id}/finish")
    def finish_learning_task(
        learning_task_id: str,
        payload: FinishMaterialQaLearningTaskRequest,
    ) -> dict[str, bool]:
        workflow.finish_learning_task(
            user_id=payload.user_id,
            book_id=payload.book_id,
            learning_task_id=learning_task_id,
        )
        return {"completed": True}

    return router
