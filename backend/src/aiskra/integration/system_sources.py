"""Порты поверх настроек модуля system: тайминг занятия (training, п. 5.2), срок хранения журнала (audit, п. 6.2)."""

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


class SystemTelephonySettings:
    """Порт `TelephonySettings` модуля training: раздел «IP-телефония» настроек администратора (п. 2.2)."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def hold_max_s(self) -> int:
        return int(merged("telephony", await SqlSettingsStore(self._s).get("telephony"))["hold_max_s"])


class SystemRetentionPolicy:
    """Порт `RetentionPolicy` модуля audit: срок хранения журнала — из настроек администратора."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def retention_days(self) -> int:
        return int(merged("audit", await SqlSettingsStore(self._s).get("audit"))["retention_days"])


class SystemServiceSwitches:
    """Порт `ServiceSwitches` модуля training (п. 2.2): переключатели подсистем — из настроек администратора."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def enabled(self, name: str) -> bool:
        values = merged("services", await SqlSettingsStore(self._s).get("services"))
        return bool(int(values.get(name, 1)))
