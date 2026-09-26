"""Точка входа FastAPI: REST (/api/v1), WebSocket (позже), /health, OpenAPI (/docs)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from aiskra.bootstrap import build_services, wire
from aiskra.modules.audit.api.router import router as audit_router
from aiskra.modules.dictionaries.api.router import router as dictionaries_router
from aiskra.modules.identity.api.router import auth_router, users_router
from aiskra.modules.incidents.api.router import router as incidents_router
from aiskra.modules.system.api.router import router as system_router
from aiskra.modules.training.api.router import router as training_router
from aiskra.platform.health import router as health_router
from aiskra.platform.services import Services
from aiskra.platform.settings import Settings
from aiskra.shared.errors import (
    AppError,
    AuthenticationError,
    DomainError,
    ExternalServiceError,
    NotFoundError,
    PermissionDeniedError,
)
from aiskra.shared.web import provide_principal

_STATUS: dict[type[AppError], int] = {
    AuthenticationError: 401,
    DomainError: 422,
    NotFoundError: 404,
    PermissionDeniedError: 403,
    ExternalServiceError: 503,
}


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    settings = settings or Settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        svc = services or build_services(settings)
        app.state.services = svc
        wire(app, svc)
        yield
        await svc.aclose()

    app = FastAPI(
        title="АИскра — тренажёр оператора 112 / ДДС",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        status = next((code for cls, code in _STATUS.items() if isinstance(exc, cls)), 500)
        return JSONResponse(status_code=status, content={"error": exc.code, "message": exc.message})

    # Запрет по умолчанию (ADR-0010): всё под /api/v1 требует сессии, кроме /auth (вход публичный,
    # остальные эндпоинты /auth сами требуют пользователя). Права уточняются require(...) в роутерах.
    signed_in = [Depends(provide_principal)]
    app.include_router(health_router)
    app.include_router(auth_router, prefix=settings.api_prefix)
    app.include_router(users_router, prefix=settings.api_prefix, dependencies=signed_in)
    app.include_router(audit_router, prefix=settings.api_prefix, dependencies=signed_in)
    app.include_router(system_router, prefix=settings.api_prefix, dependencies=signed_in)
    app.include_router(dictionaries_router, prefix=settings.api_prefix, dependencies=signed_in)
    app.include_router(incidents_router, prefix=settings.api_prefix, dependencies=signed_in)
    app.include_router(training_router, prefix=settings.api_prefix, dependencies=signed_in)
    return app


app = create_app()
