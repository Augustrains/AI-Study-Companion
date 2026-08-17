from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from modules.common.auth import CurrentUser, IdentityResolver
from modules.common.errors import ValidationAppError

from .schemas import ProfileWorkflowReviewRequest, ProfileWorkflowStartRequest
from .workflow import LearnerProfileWorkflow


def build_router(
    module: LearnerProfileWorkflow,
    identity: IdentityResolver | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/learner-profile", tags=["learner-profile"])
    identity = identity or IdentityResolver()
    current_user_dependency = Depends(identity)

    @router.get("")
    def get_profile(
        user_id: str = Query(..., min_length=1),
        learning_domain: str = "",
        current_user: CurrentUser = current_user_dependency,
    ) -> dict[str, Any]:
        actor = identity.require_claimed_user(current_user, user_id)
        profile = module.get(actor, learning_domain.strip() or None)
        return {
            "exists": profile is not None,
            "profile": profile.to_dict() if profile else None,
        }

    @router.get("/knowledge-points")
    def get_knowledge_points(
        learning_domain: str = Query(..., min_length=1),
    ) -> dict[str, Any]:
        return {
            "learningDomain": learning_domain,
            "knowledgePoints": module.knowledge_points(learning_domain),
        }

    @router.post("/workflows", status_code=201)
    def start_workflow(
        payload: ProfileWorkflowStartRequest,
        current_user: CurrentUser = current_user_dependency,
    ) -> dict[str, Any]:
        try:
            actor = identity.require_claimed_user(current_user, payload.user_id)
            data = payload.model_dump(exclude_none=True)
            data["user_id"] = actor
            draft = module.start_workflow(data)
        except (ValidationAppError, ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)}
            ) from exc
        return {
            "workflowId": draft["workflow_id"],
            "status": "pending_confirmation",
            "draft": draft["draft_profile"],
            "allowedActions": draft["allowed_actions"],
        }

    @router.post("/workflows/{workflow_id}/review")
    def review_workflow(
        workflow_id: str,
        payload: ProfileWorkflowReviewRequest,
        current_user: CurrentUser = current_user_dependency,
    ) -> dict[str, Any]:
        try:
            profile = module.review_workflow(
                workflow_id,
                action=payload.action.strip(),
                corrections=payload.corrections,
                actor_user_id=current_user.user_id,
            )
        except (KeyError, RuntimeError, ValueError) as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "WORKFLOW_STATE_ERROR", "message": str(exc)},
            ) from exc
        if profile is None:
            return {"status": "rejected", "profile": None}
        return {"status": "completed", "exists": True, "profile": profile.to_dict()}

    return router
