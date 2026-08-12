"""诊断模块 HTTP 接口。

本文件只负责前后端交互：接收 Pydantic 请求对象、调用诊断业务模块、
返回业务结果。字段校验由请求/响应 Schema 和诊断字段规则负责，业务
异常由 API 全局异常处理器统一转换为 HTTP 响应。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .diagnosis_workflow import DiagnosisWorkflow
from .schemas import (
    DiagnosticAnswerRequest,
    DiagnosticAnswerResponse,
    DiagnosticCalibrationRequest,
    DiagnosticCalibrationResponse,
    DiagnosticFinishResponse,
    DiagnosticStartRequest,
    DiagnosticStartResponse,
)

# 前端简写与实际题库文件名之间的映射。
BOOK_TO_QUESTION_BANK = {"ml": "ml-001", "dl": "dl-001"}


def build_router(workflow: DiagnosisWorkflow) -> APIRouter:
    """创建诊断路由，并将请求转交给统一诊断工作流。"""
    router = APIRouter(tags=["diagnosis"])

    @router.post("/api/diagnostics/start", response_model=DiagnosticStartResponse)
    def start_diagnostic(payload: DiagnosticStartRequest) -> dict[str, Any]:
        """启动诊断并返回题目；异常由全局异常处理器统一处理。"""
        book_id = BOOK_TO_QUESTION_BANK.get(payload.book_id, payload.book_id)
        result = workflow.start_diagnosis(
            user_id=payload.user_id,
            book_id=book_id,
            learning_goal=payload.learning_goal,
        )
        return result

    @router.post("/api/diagnostics/{diagnostic_id}/answers", response_model=DiagnosticAnswerResponse)
    def submit_answer(diagnostic_id: str, payload: DiagnosticAnswerRequest) -> dict[str, Any]:
        """提交答案并返回保存结果。"""
        return workflow.submit_answer(
            diagnostic_id,
            payload.question_id,
            payload.answer,
            payload.skipped,
        )

    @router.post("/api/diagnostics/{diagnostic_id}/finish", response_model=DiagnosticFinishResponse)
    async def finish_diagnostic(diagnostic_id: str) -> dict[str, Any]:
        """完成诊断并返回待审核摘要。"""
        return await workflow.finish_diagnosis(diagnostic_id)

    @router.post("/api/learner-calibrations", response_model=DiagnosticCalibrationResponse)
    def submit_calibration(payload: DiagnosticCalibrationRequest) -> dict[str, Any]:
        """提交用户校准结果并返回保存状态。"""
        result = workflow.confirm_diagnosis(
            payload.diagnostic_id,
            calibration=payload.level,
            reason=payload.reason,
        )
        return {"diagnostic_id": payload.diagnostic_id, "saved": result is not None}

    return router
