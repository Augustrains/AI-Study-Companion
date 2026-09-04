"""Production ASGI entry point used by the unified PowerShell starter."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from bootstrap.application import ApiDependencies, build_api_dependencies
from modules.common.config import Settings

from .server import create_app


dependencies: ApiDependencies = build_api_dependencies(Settings.from_env())


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    dependencies.start()
    try:
        yield
    finally:
        dependencies.close()


app = create_app(dependencies, lifespan=lifespan)
