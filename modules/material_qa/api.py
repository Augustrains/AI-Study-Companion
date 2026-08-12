from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .schemas import (
    AskMaterialQuestionRequest,
    AskMaterialQuestionResponse,
    CreateMaterialQaConversationRequest,
    CreateMaterialQaConversationResponse,
)
from .models import MaterialQaAnswer, MaterialQaConversation
from .workflow import MaterialQaWorkflow


def build_router(workflow: MaterialQaWorkflow) -> APIRouter:
    router = APIRouter(tags=["material-qa"])

    def conversation_response(conversation: MaterialQaConversation) -> dict[str, Any]:
        return {
            "conversation_id": conversation.conversation_id,
            "book_id": conversation.book_id,
            "user_id": conversation.user_id,
            "created_at": conversation.created_at,
            "status": "active",
        }

    def answer_response(answer: MaterialQaAnswer, request_id: str) -> dict[str, Any]:
        return {
            "answer": answer.answer,
            "citations": answer.citations,
            "related_knowledge_points": answer.related_knowledge_points,
            "recommended_action": answer.recommended_action,
            "conversation_id": answer.conversation_id,
            "request_id": request_id,
        }

    @router.post("/api/rag/conversations", response_model=CreateMaterialQaConversationResponse)
    def create_conversation(payload: CreateMaterialQaConversationRequest) -> dict[str, Any]:
        return conversation_response(workflow.create_conversation(book_id=payload.book_id, user_id=payload.user_id))

    @router.post("/api/rag/conversations/{conversation_id}/messages", response_model=AskMaterialQuestionResponse)
    def ask_in_conversation(conversation_id: str, payload: AskMaterialQuestionRequest) -> dict[str, Any]:
        result = workflow.ask(
            conversation_id=conversation_id,
            book_id=payload.book_id,
            question=payload.question,
            source_ids=payload.source_ids,
        )
        return answer_response(result, f"req-{conversation_id}")

    @router.post("/api/rag/ask", response_model=AskMaterialQuestionResponse)
    def ask_material_question(payload: AskMaterialQuestionRequest) -> dict[str, Any]:
        conversation_id = payload.conversation_id
        if conversation_id is None:
            conversation_id = workflow.create_conversation(book_id=payload.book_id, user_id=payload.user_id).conversation_id
        result = workflow.ask(
            conversation_id=conversation_id,
            book_id=payload.book_id,
            question=payload.question,
            source_ids=payload.source_ids,
        )
        return answer_response(result, f"req-{conversation_id}")

    return router
