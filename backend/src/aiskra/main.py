"""Точка входа FastAPI: REST (/api/v1), WebSocket (позже), /health, OpenAPI (/docs)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from aiskra.ai.config import load_ai_config
from aiskra.bootstrap import build_services, daily_backup_loop, wire
from aiskra.modules.assessment.api.router import router as assessment_router
from aiskra.modules.audit.api.router import router as audit_router
from aiskra.modules.dictionaries.api.router import router as dictionaries_router
from aiskra.modules.identity.api.router import auth_router, demo_router, groups_router, users_router
from aiskra.modules.incidents.api.router import router as incidents_router
from aiskra.modules.system.api.router import router as system_router
from aiskra.modules.training.api.router import router as training_router
from aiskra.platform.api_docs import mount_admin_docs
from aiskra.platform.health import router as health_router
from aiskra.platform.security_headers import SecurityHeadersMiddleware
from aiskra.platform.services import Services
from aiskra.platform.settings import Settings
from aiskra.platform.startup_checks import UnsafeConfigError, check_startup
from aiskra.platform.validation_ru import translate
from aiskra.shared.errors import (
    AppError,
    AuthenticationError,
    DomainError,
    ExternalServiceError,
    NotFoundError,
    PermissionDeniedError,
    TooManyRequestsError,
)
from aiskra.shared.web import provide_principal

log = logging.getLogger(__name__)

_STATUS: dict[type[AppError], int] = {
    AuthenticationError: 401,
    DomainError: 422,
    NotFoundError: 404,
    PermissionDeniedError: 403,
    ExternalServiceError: 503,
    TooManyRequestsError: 429,
}


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    settings = settings or Settings()
    logging.basicConfig(level=settings.effective_log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger().setLevel(settings.effective_log_level)  # basicConfig не меняет уже настроенный корень
    # F6.3 (ADR-0015): в prod небезопасные настройки останавливают запуск сразу, в demo и dev — предупреждения
    check_startup(settings, services.ai_config if services else load_ai_config(settings.ai_config_path))
    public_docs = settings.expose_docs and not settings.docs_admin_only

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        svc = services or build_services(settings)
        app.state.services = svc
        app.state.started_at = datetime.now(UTC)  # время старта — в /health
        wire(app, svc)
        backup_job = asyncio.create_task(daily_backup_loop(svc)) if settings.scheduler_enabled else None
        yield
        if backup_job:
            backup_job.cancel()
        await svc.aclose()

    app = FastAPI(
        title="АИскра — тренажёр оператора 112 / ДДС",
        version=settings.version,
        lifespan=lifespan,
        docs_url="/docs" if public_docs else None,
        openapi_url="/openapi.json" if public_docs else None,
    )
    if settings.expose_docs and settings.docs_admin_only:
        mount_admin_docs(app)  # prod: Swagger и схема API — только вошедшему администратору
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=1024)  # справочники и журналы — JSON в сотни КБ (6.1)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        # п. 6.2: внутренности (трассировка, SQL, пути) — только в лог, клиенту — единый ответ
        log.exception("Необработанная ошибка %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500, content={"error": "internal_error", "message": "Внутренняя ошибка сервера"}
        )

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content=translate(list(exc.errors())))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # «Not Found», «Method Not Allowed» и т. п. — тоже по-русски и в общем формате (6.3)
        titles = {404: "Не найдено", 405: "Метод не поддерживается", 401: "Требуется вход в систему"}
        message = titles.get(exc.status_code) or (exc.detail if isinstance(exc.detail, str) else "Ошибка запроса")
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": "http_error", "message": message},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        status = next((code for cls, code in _STATUS.items() if isinstance(exc, cls)), 500)
        return JSONResponse(status_code=status, content={"error": exc.code, "message": exc.message})

    # Запрет по умолчанию (ADR-0010): всё под /api/v1 требует сессии, кроме /auth (вход публичный,
    # остальные эндпоинты /auth сами требуют пользователя; демо-вход F2 публичен только в demo и dev).
    # Права уточняются require(...) в роутерах.
    signed_in = [Depends(provide_principal)]
    app.include_router(health_router)
    app.include_router(auth_router, prefix=settings.api_prefix)
    if settings.demo_enabled:  # F2: демо-вход без пароля — только demo и dev; в prod маршрутов нет (404)
        app.include_router(demo_router, prefix=settings.api_prefix)
    app.include_router(users_router, prefix=settings.api_prefix, dependencies=signed_in)
    app.include_router(groups_router, prefix=settings.api_prefix, dependencies=signed_in)
    app.include_router(audit_router, prefix=settings.api_prefix, dependencies=signed_in)
    app.include_router(system_router, prefix=settings.api_prefix, dependencies=signed_in)
    app.include_router(dictionaries_router, prefix=settings.api_prefix, dependencies=signed_in)
    app.include_router(incidents_router, prefix=settings.api_prefix, dependencies=signed_in)
    app.include_router(training_router, prefix=settings.api_prefix, dependencies=signed_in)
    app.include_router(assessment_router, prefix=settings.api_prefix, dependencies=signed_in)
    return app


try:
    app = create_app()
except UnsafeConfigError as exc:  # uvicorn aiskra.main:app — понятное сообщение без трассировки, код выхода 1
    raise SystemExit(exc.message) from None
