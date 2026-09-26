"""Порт `SessionDefaults` модуля training поверх настроек модуля system (п. 5.2)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.system.application.commands.settings import merged
from aiskra.modules.system.infrastructure.settings import SqlSettingsStore


class SystemSessionDefaults:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self) -> dict[str, Any]:
        values = merged("session_defaults", await SqlSettingsStore(self._s).get("session_defaults"))
        return {k: int(v) if k in ("difficulty", "max_waiting") else v for k, v in values.items()}
