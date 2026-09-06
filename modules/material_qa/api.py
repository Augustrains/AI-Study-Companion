from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, Query, UploadFile

from modules.common.errors import ConfigurationError

from .schemas import (
    AskMaterialQuestionRequest,
    AskMaterialQuestionResponse,
    CreateMaterialQaConversationRequest,
    CreateMaterialQaConversationResponse,
    FinishMaterialQaLearningTaskRequest,
    MaterialQaAttachmentResponse,
)
from .attachment_service import MaterialQaAttachmentService
from .models import (
    MaterialQaAnswer,
    MaterialQaAttachment,
    MaterialQaConversation,
    MaterialQaPendingAttachment,
)
from .workflow import MaterialQaWorkflow


def build_router(
    workflow: MaterialQaWorkflow,
    attachment_service: MaterialQaAttachmentService | None = None,
) -> APIRouter:
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
            "user_message_id": answer.user_message_id,
        }

    # 确保附件功能已经在应用启动阶段完成装配。
    def require_attachment_service() -> MaterialQaAttachmentService:
        if attachment_service is None:
            raise ConfigurationError("material QA attachment service is not configured")
        return attachment_service

    # 将内部附件模型转换成符合前端响应协议的字典。
    def attachment_response(attachment: MaterialQaAttachment) -> dict[str, Any]:
        return {
            "id": attachment.id,
            "message_id": attachment.message_id,
            "file_name": attachment.file_name,
            "file_type": attachment.file_type,
            "file_size": attachment.file_size,
            "file_url": attachment.file_url,
            "created_at": attachment.created_at,
            "updated_at": attachment.updated_at,
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

    # 接收一个问题和一个附件，在同一条用户消息下完成保存与绑定。
    @router.post(
        "/api/rag/conversations/{conversation_id}/messages-with-attachment",
        response_model=AskMaterialQuestionResponse,
    )
    async def ask_with_attachment(
        conversation_id: str,
        user_id: str = Form(..., alias="userId", min_length=1),
        book_id: str = Form(..., alias="bookId", min_length=1),
        question: str = Form(..., min_length=1, max_length=2000),
        allow_general_fallback: bool = Form(False, alias="allowGeneralFallback"),
        answer_mode: str = Form("direct", alias="answerMode", pattern="^(direct|socratic)$"),
        learning_task_id: str | None = Form(None, alias="learningTaskId", max_length=64),
        file: UploadFile = File(...),
    ) -> dict[str, Any]:
        result = workflow.ask(
            conversation_id=conversation_id,
            user_id=user_id,
            book_id=book_id,
            question=question,
            allow_general_fallback=allow_general_fallback,
            answer_mode=answer_mode,  # type: ignore[arg-type]
            learning_task_id=learning_task_id,
            attachments=[
                MaterialQaPendingAttachment(
                    file_name=file.filename or "",
                    file_type=file.content_type or "application/octet-stream",
                    content=await file.read(),
                )
            ],
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

    # 接收multipart文件并交给附件业务层完成校验、上传和数据库保存。
    @router.post("/api/rag/attachments", response_model=MaterialQaAttachmentResponse)
    async def upload_attachment(
        user_id: str = Form(..., alias="userId", min_length=1),
        message_id: int = Form(..., alias="messageId", gt=0),
        file: UploadFile = File(...),
    ) -> dict[str, Any]:
        content = await file.read()
        attachment = require_attachment_service().upload(
            user_id=user_id,
            message_id=message_id,
            file_name=file.filename or "",
            file_type=file.content_type or "application/octet-stream",
            content=content,
        )
        return attachment_response(attachment)

    # 返回当前用户指定问答消息下的所有附件元数据。
    @router.get(
        "/api/rag/messages/{message_id}/attachments",
        response_model=list[MaterialQaAttachmentResponse],
    )
    def list_message_attachments(
        message_id: int,
        user_id: str = Query(..., alias="userId", min_length=1),
    ) -> list[dict[str, Any]]:
        attachments = require_attachment_service().list_for_message(
            user_id=user_id,
            message_id=message_id,
        )
        return [attachment_response(item) for item in attachments]

    # 删除当前用户有权操作的附件记录及对应OSS对象。
    @router.delete("/api/rag/attachments/{attachment_id}")
    def delete_attachment(
        attachment_id: int,
        user_id: str = Query(..., alias="userId", min_length=1),
    ) -> dict[str, bool]:
        require_attachment_service().delete(
            user_id=user_id,
            attachment_id=attachment_id,
        )
        return {"deleted": True}

    return router
