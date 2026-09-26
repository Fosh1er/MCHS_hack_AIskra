"""SQL-хранилище настроек системы."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.system.infrastructure.models import SystemSettingModel


class SqlSettingsStore:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, key: str) -> dict[str, Any] | None:
        row = await self._s.get(SystemSettingModel, key)
        return dict(row.value) if row else None

    async def put(self, key: str, value: dict[str, Any], actor_id: UUID) -> None:
        row = await self._s.get(SystemSettingModel, key)
        if row is None:
            self._s.add(SystemSettingModel(key=key, value=value, updated_by=actor_id))
        else:
            row.value = value
            row.updated_by = actor_id
        await self._s.flush()
