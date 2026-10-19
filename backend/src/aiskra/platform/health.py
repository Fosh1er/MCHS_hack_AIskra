"""Проверка работоспособности (ТЗ: мониторинг, health-checks). Используется docker compose и админкой."""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Request

from aiskra.platform.db import ping
from aiskra.platform.services import Services

router = APIRouter(tags=["health"])


@router.get("/health", summary="Состояние сервиса")
async def health(request: Request) -> dict[str, Any]:
    services = cast(Services, request.app.state.services)
    db_ok = await ping(services.engine)
    stats = services.cache.stats()
    started_at = getattr(request.app.state, "started_at", None)
    return {
        "status": "ok" if db_ok else "degraded",
        # F6.3 (ADR-0015): режим окружения, версия сборки (git sha из AISKRA_VERSION, иначе unknown), время старта
        "env": services.settings.app_env,
        "version": services.settings.version,
        "started_at": started_at.isoformat() if started_at else None,
        "db": "ok" if db_ok else "unavailable",
        "ai": {
            "allow_external": services.ai_config.allow_external,
            "default_provider": services.ai_config.default_provider,
            "cache": {
                "hits": stats.hits,
                "misses": stats.misses,
                "size": stats.size,
                "hit_rate": round(stats.hit_rate, 3),
            },
        },
    }
