from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from modules.common.errors import ValidationAppError

from .schemas import ProfileWorkflowReviewRequest, ProfileWorkflowStartRequest
from .workflow import LearnerProfileWorkflow


def build_router(module: LearnerProfileWorkflow) -> APIRouter:
    router = APIRouter(prefix="/api/learner-profile", tags=["learner-profile"])

    @router.get("")
    def get_profile(user_id: str = Query(..., min_length=1), learning_domain: str = "") -> dict[str, Any]:
        profile = module.get(user_id.strip(), learning_domain.strip() or None)
        return {"exists": profile is not None, "profile": profile.to_dict() if profile else None}

    @router.get("/knowledge-points")
    def get_knowledge_points(learning_domain: str = Query(..., min_length=1)) -> dict[str, Any]:
        return {"learningDomain": learning_domain, "knowledgePoints": module.knowledge_points(learning_domain)}

    @router.post("/workflows", status_code=201)
    def start_workflow(payload: ProfileWorkflowStartRequest) -> dict[str, Any]:
        try:
            draft = module.start_workflow(payload.model_dump(exclude_none=True))
        except (ValidationAppError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)}) from exc
        return {
            "workflowId": draft["workflow_id"],
            "status": "pending_confirmation",
            "draft": draft["draft_profile"],
            "allowedActions": draft["allowed_actions"],
        }

    @router.post("/workflows/{workflow_id}/review")
    def review_workflow(workflow_id: str, payload: ProfileWorkflowReviewRequest) -> dict[str, Any]:
        try:
            profile = module.review_workflow(
                workflow_id,
                action=payload.action.strip(),
                corrections=payload.corrections,
            )
        except (KeyError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail={"code": "WORKFLOW_STATE_ERROR", "message": str(exc)}) from exc
        if profile is None:
            return {"status": "rejected", "profile": None}
        return {"status": "completed", "exists": True, "profile": profile.to_dict()}

    return router
