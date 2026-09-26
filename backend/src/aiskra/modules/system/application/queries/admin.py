"""Запросы панели администратора: состояние сервисов (health-checks) и последние записи лога."""

from __future__ import annotations

from dataclasses import dataclass

from aiskra.modules.system.application.ports.admin import LogRecord, LogSource, ServiceState, StatusSource
from aiskra.shared.application import Query
from aiskra.shared.errors import DomainError

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


@dataclass(frozen=True, kw_only=True)
class GetStatus(Query):
    pass


class GetStatusHandler:
    def __init__(self, source: StatusSource) -> None:
        self._source = source

    async def __call__(self, q: GetStatus) -> list[ServiceState]:
        return await self._source.services()


@dataclass(frozen=True, kw_only=True)
class RecentLogs(Query):
    level: str = "INFO"
    limit: int = 200
    q: str = ""


class RecentLogsHandler:
    def __init__(self, source: LogSource) -> None:
        self._source = source

    async def __call__(self, q: RecentLogs) -> list[LogRecord]:
        if q.level.upper() not in LEVELS:
            raise DomainError("Уровень — DEBUG, INFO, WARNING или ERROR", code="bad_level")
        return self._source.recent(level=q.level.upper(), limit=max(1, min(q.limit, 1000)), q=q.q.strip())
