"""Общие FastAPI-зависимости уровня платформы (используются только composition root)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.platform.services import Services


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Сессия БД на запрос: откат при исключении, закрытие всегда."""
    services = cast(Services, request.app.state.services)
    async with services.session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
