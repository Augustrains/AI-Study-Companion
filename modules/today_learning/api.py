from __future__ import annotations

from fastapi import APIRouter, Query

from .module import TodayLearningModule
from .schemas import TodayLearningResponse


def build_router(module: TodayLearningModule) -> APIRouter:
    router = APIRouter(tags=["today-learning"])

    @router.get("/api/today-learning", response_model=TodayLearningResponse)
    def get_today_learning(
        user_id: str = Query(..., alias="userId", min_length=1),
        book_id: str = Query(..., alias="bookId", min_length=1),
    ) -> dict:
        return module.get_today_learning(user_id=user_id, book_id=book_id)

    return router

