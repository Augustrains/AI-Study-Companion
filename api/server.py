from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from modules.diagnosis.api import build_router as build_diagnosis_router
from modules.learner_profile.api import build_router as build_profile_router


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

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"code": "INVALID_REQUEST", "message": "request validation failed", "retryable": False, "details": exc.errors()},
        )

    app.include_router(build_profile_router(dependencies.profile))
    app.include_router(build_diagnosis_router(dependencies.diagnosis))
    return app
