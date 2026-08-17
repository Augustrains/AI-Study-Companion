from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from modules.common.auth import CurrentUser, IdentityResolver

from .models import MaterialQaAnswer, MaterialQaConversation
from .schemas import (
    AskMaterialQuestionRequest,
    AskMaterialQuestionResponse,
    CreateMaterialQaConversationRequest,
    CreateMaterialQaConversationResponse,
    MaterialQaConversationHistoryResponse,
)
from .workflow import MaterialQaWorkflow


def build_router(
    workflow: MaterialQaWorkflow,
    identity: IdentityResolver | None = None,
) -> APIRouter:
    router = APIRouter(tags=["material-qa"])
    identity = identity or IdentityResolver()
    current_user_dependency = Depends(identity)

    def conversation_response(conversation: MaterialQaConversation) -> dict[str, Any]:
        return {
            "conversation_id": conversation.conversation_id,
            "book_id": conversation.book_id,
            "user_id": conversation.user_id,
            "created_at": conversation.created_at,
            "status": "active",
        }

    def answer_response(answer: MaterialQaAnswer) -> dict[str, Any]:
        return {
            "answer": answer.answer,
            "refused": answer.refused,
            "citations": answer.citations,
            "related_knowledge_points": answer.related_knowledge_points,
            "recommended_action": answer.recommended_action,
            "conversation_id": answer.conversation_id,
            "request_id": answer.request_id,
        }

    @router.post(
        "/api/rag/conversations", response_model=CreateMaterialQaConversationResponse
    )
    def create_conversation(
        payload: CreateMaterialQaConversationRequest,
        current_user: CurrentUser = current_user_dependency,
    ) -> dict[str, Any]:
        actor = identity.require_claimed_user(current_user, payload.user_id)
        return conversation_response(
            workflow.create_conversation(book_id=payload.book_id, user_id=actor)
        )

    @router.post(
        "/api/rag/conversations/{conversation_id}/messages",
        response_model=AskMaterialQuestionResponse,
    )
    def ask_in_conversation(
        conversation_id: str,
        payload: AskMaterialQuestionRequest,
        current_user: CurrentUser = current_user_dependency,
    ) -> dict[str, Any]:
        actor = identity.require_claimed_user(current_user, payload.user_id)
        result = workflow.ask(
            conversation_id=conversation_id,
            book_id=payload.book_id,
            question=payload.question,
            source_ids=payload.source_ids,
            actor_user_id=actor,
            request_id=payload.request_id,
        )
        return answer_response(result)

    @router.get(
        "/api/rag/conversations/{conversation_id}/messages",
        response_model=MaterialQaConversationHistoryResponse,
    )
    def get_conversation_messages(
        conversation_id: str,
        book_id: str = Query(alias="bookId", min_length=1),
        current_user: CurrentUser = current_user_dependency,
    ) -> dict[str, Any]:
        return {
            "conversation_id": conversation_id,
            "book_id": book_id,
            "messages": workflow.conversation_history(
                conversation_id=conversation_id,
                book_id=book_id,
                actor_user_id=current_user.user_id,
            ),
        }

    @router.post("/api/rag/ask", response_model=AskMaterialQuestionResponse)
    def ask_material_question(
        payload: AskMaterialQuestionRequest,
        current_user: CurrentUser = current_user_dependency,
    ) -> dict[str, Any]:
        actor = identity.require_claimed_user(current_user, payload.user_id)
        conversation_id = payload.conversation_id
        if conversation_id is None:
            conversation_id = workflow.create_conversation(
                book_id=payload.book_id,
                user_id=actor,
            ).conversation_id
        result = workflow.ask(
            conversation_id=conversation_id,
            book_id=payload.book_id,
            question=payload.question,
            source_ids=payload.source_ids,
            actor_user_id=actor,
            request_id=payload.request_id,
        )
        return answer_response(result)

    return router
