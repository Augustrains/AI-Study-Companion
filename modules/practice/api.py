from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from .repository import PracticeRepository

class StartRequest(BaseModel):
    userId: int = Field(gt=0)
    bookId: str = Field(min_length=1)

class AnswerRequest(BaseModel):
    userId: int = Field(gt=0)
    questionId: int = Field(gt=0)
    answer: str = Field(min_length=1)

class AchievementNoticeRequest(BaseModel):
    userId: int = Field(gt=0)

def build_router(repository: PracticeRepository) -> APIRouter:
    router = APIRouter(prefix="/api/practice", tags=["practice"])
    @router.post("/sessions")
    def start(payload: StartRequest): return repository.start(user_id=payload.userId, book_id=repository.resolve_book_id(payload.bookId))
    @router.get("/sessions/{session_id}/next")
    def next_question(session_id: int, userId: int = Query(gt=0)): return {"question": repository.next_question(session_id=session_id, user_id=userId)}
    @router.post("/sessions/{session_id}/answers")
    def answer(session_id: int, payload: AnswerRequest): return repository.answer(session_id=session_id, user_id=payload.userId, question_id=payload.questionId, answer=payload.answer)
    @router.post("/sessions/{session_id}/finish")
    def finish(session_id: int, userId: int = Query(gt=0)): return repository.finish(session_id=session_id, user_id=userId)
    @router.get("/leaderboard")
    def leaderboard(period: Literal["week", "month"] = "week", limit: int = Query(20, ge=1, le=100)): return {"items": repository.leaderboard(period=period, limit=limit)}
    @router.get("/overview")
    def overview(userId: int = Query(gt=0), period: Literal["week", "month"] = "week"): return repository.overview(user_id=userId, period=period)
    @router.get("/achievements")
    # 首屏只读勋章定义和获奖记录，避免完整统计阻塞页面。
    def achievements(userId: int = Query(gt=0)): return repository.achievements(user_id=userId)
    @router.get("/achievements/progress")
    # 仅在答题、完成任务或后台刷新时计算完整进度；默认复用 5 分钟缓存。
    def achievement_progress(userId: int = Query(gt=0), force: bool = False):
        return repository.achievement_progress(user_id=userId, force=force)
    @router.post("/achievements/{achievement_id}/acknowledge")
    # 用户关闭解锁弹窗后确认通知，防止下次进入页面重复弹出。
    def acknowledge_achievement(achievement_id: int, payload: AchievementNoticeRequest):
        return repository.acknowledge_achievement(user_id=payload.userId, achievement_id=achievement_id)
    return router
