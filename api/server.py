from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from modules.auth.api import build_router as build_auth_router
from modules.auth.module import AuthModule
from modules.common import api as common_api
from modules.learner_goals.api import build_router as build_learner_goal_router
from modules.learner_goals.module import LearnerGoalModule
from modules.diagnosis.api import build_router as build_diagnosis_router
from modules.learner_profile.api import build_router as build_profile_router
from modules.learning_plan.api import build_router as build_learning_plan_router
from modules.material_qa.api import build_router as build_material_qa_router
from modules.learning_record.api import build_router as build_learning_record_router
from modules.learning_resources.api import build_router as build_learning_resource_router
from modules.learning_resources.module import LearningResourceModule
from modules.today_learning.api import build_router as build_today_learning_router


logger = logging.getLogger(__name__)


#创建实例
def create_app(dependencies: Any) -> FastAPI:
    """Create the application and register feature-owned API routers."""
    app = FastAPI(title="Study Companion API", version="1.0.0")

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": f"HTTP_{exc.status_code}", "message": str(exc.detail), "retryable": exc.status_code >= 500},
        )

    #统一处理错误
    @app.exception_handler(common_api.errors.AppError)
    async def app_error_handler(_request: Request, exc: common_api.errors.AppError) -> JSONResponse:
        if exc.cause is not None:
            logger.error(
                "application error: code=%s details=%s",
                exc.code,
                exc.details,
                exc_info=(type(exc.cause), exc.cause, exc.cause.__traceback__),
            )
        else:
            logger.warning("application error: code=%s details=%s", exc.code, exc.details)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message or exc.code,
                "retryable": exc.retryable,
                "details": exc.details,
            },
        )

    #注册全局异常处理
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # 将 FastAPI/Pydantic 的异常转换为 common 统一异常语义。
        app_error = common_api.errors.RequestValidationAppError(
            "request validation failed",
            details={"issues": exc.errors()},
        )
        return JSONResponse(
            status_code=app_error.status_code,
            content={
                "code": app_error.code,
                "message": app_error.message,
                "retryable": app_error.retryable,
                "details": app_error.details,
            },
        )

    #注册业务模块路由
    # 认证：不依赖其它模块，单独持有 data/auth/users.json，并在启动时确保体验账号存在。
    app.include_router(build_auth_router(getattr(dependencies, "auth", None) or AuthModule()))
    app.include_router(build_learner_goal_router(getattr(dependencies, "learner_goals", None) or LearnerGoalModule(), dependencies.learning_plan))
    app.include_router(build_profile_router(dependencies.profile))
    app.include_router(build_diagnosis_router(dependencies.diagnosis))
    app.include_router(build_learning_plan_router(dependencies.learning_plan))
    app.include_router(build_material_qa_router(dependencies.material_qa))
    app.include_router(build_learning_record_router(dependencies.learning_record, dependencies.learning_plan))
    app.include_router(build_today_learning_router(dependencies.today_learning))
    # 延伸学习资源：只读本地资源文件，无需注入依赖。
    app.include_router(build_learning_resource_router(getattr(dependencies, "learning_resources", None) or LearningResourceModule()))
    return app
