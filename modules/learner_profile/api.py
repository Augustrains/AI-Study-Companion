from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from modules.common.errors import ValidationAppError

from .module import MySqlLearnerProfileModule
from .schemas import ProfileSetupRequest


def build_router(module: MySqlLearnerProfileModule) -> APIRouter:
    router = APIRouter(prefix="/api/learner-profile", tags=["learner-profile"])

    @router.get("/books")
    def list_books() -> dict[str, Any]:
        return {"books": module.books()}

    @router.get("/setup")
    def get_setup(user_id: int = Query(..., gt=0), book_id: int = Query(..., gt=0)) -> dict[str, Any]:
        profile = module.get_setup(user_id, book_id)
        return {"exists": profile is not None, "profile": profile}

    @router.post("/setup")
    def save_setup(payload: ProfileSetupRequest) -> dict[str, Any]:
        try:
            profile = module.save_setup(payload.model_dump())
        except (ValidationAppError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)}) from exc
        return {"exists": True, "profile": profile}

    return router
