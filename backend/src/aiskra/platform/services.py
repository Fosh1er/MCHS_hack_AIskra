"""Контейнер сервисов процесса. Собирается в composition root, хранится в app.state.services."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from aiskra.ai.config import AIConfig
from aiskra.ai.ports import STTPort, TTSPort
from aiskra.ai.router import ModelRouter
from aiskra.platform.settings import Settings
from aiskra.shared.cache import CachePort


@dataclass
class Services:
    settings: Settings
    ai_config: AIConfig
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    cache: CachePort
    model_router: ModelRouter
    tts: TTSPort
    stt: STTPort

    async def aclose(self) -> None:
        await self.model_router.aclose()
        await self.engine.dispose()
