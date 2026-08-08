from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from .module import DiagnosisModule
from .schemas import DiagnosticAnswerRequest, DiagnosticCalibrationRequest, DiagnosticStartRequest

BOOK_TO_QUESTION_BANK = {"ml": "machine_learning", "rl": "reinforcement_learning"}


def build_router(module: DiagnosisModule) -> APIRouter:
    router = APIRouter(tags=["diagnosis"])

    @router.post("/api/diagnostics/start")
    def start_diagnostic(payload: DiagnosticStartRequest) -> dict[str, Any]:
        book_id = BOOK_TO_QUESTION_BANK.get(payload.book_id, payload.book_id)
        if not book_id.strip():
            raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": "bookId is required"})
        try:
            result = module.start(
                user_id=payload.user_id.strip() or "user_001",
                book_id=book_id,
                learning_goal=payload.learning_goal,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail={"code": "QUESTION_BANK_NOT_FOUND", "message": str(exc)}) from exc
        return {"diagnosticId": result["diagnostic_id"], "questions": result["questions"]}

    @router.post("/api/diagnostics/{diagnostic_id}/answers")
    def submit_answer(diagnostic_id: str, payload: DiagnosticAnswerRequest) -> dict[str, Any]:
        try:
            return module.submit_answer(diagnostic_id, payload.question_id, payload.answer, payload.skipped)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)}) from exc

    @router.post("/api/diagnostics/{diagnostic_id}/finish")
    def finish_diagnostic(diagnostic_id: str) -> dict[str, Any]:
        try:
            result = module.finish(diagnostic_id)
        except (KeyError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail={"code": "DIAGNOSTIC_STATE_ERROR", "message": str(exc)}) from exc
        return {"diagnosticId": result["diagnostic_id"], **{key: result[key] for key in ("level", "accuracy", "confidence", "evidence", "suggestions")}}

    @router.post("/api/learner-calibrations")
    def submit_calibration(payload: DiagnosticCalibrationRequest) -> dict[str, Any]:
        if payload.level not in {"lower", "same", "higher"}:
            raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": "unsupported calibration level"})
        try:
            result = module.review(payload.diagnostic_id, calibration=payload.level, reason=payload.reason)
        except (KeyError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail={"code": "DIAGNOSTIC_STATE_ERROR", "message": str(exc)}) from exc
        return {"diagnosticId": payload.diagnostic_id, "saved": result is not None}

    return router
