from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from modules.common.auth import CurrentUser, IdentityResolver

from .module import TodayLearningModule
from .schemas import TodayLearningResponse


def build_router(
    module: TodayLearningModule,
    identity: IdentityResolver | None = None,
) -> APIRouter:
    router = APIRouter(tags=["today-learning"])
    identity = identity or IdentityResolver()
    current_user_dependency = Depends(identity)

    @router.get("/api/today-learning", response_model=TodayLearningResponse)
    def get_today_learning(
        user_id: str = Query(..., alias="userId", min_length=1),
        book_id: str = Query(..., alias="bookId", min_length=1),
        current_user: CurrentUser = current_user_dependency,
    ) -> dict:
        actor = identity.require_claimed_user(current_user, user_id)
        return module.get_today_learning(user_id=actor, book_id=book_id)

    return router
