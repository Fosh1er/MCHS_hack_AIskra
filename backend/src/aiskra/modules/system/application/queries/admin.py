"""Запросы панели администратора: состояние сервисов (health-checks), последние записи лога и оповещения о сбоях."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

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


@dataclass(frozen=True, kw_only=True)
class GetAlerts(Query):
    window_min: int = 60  # ошибки лога — за последний час


@dataclass(frozen=True)
class Alert:
    level: str  # warn | critical
    source: str
    text: str
    at: datetime | None = None


class GetAlertsHandler:
    """Оповещения администратора о сбоях (п. 10.6): сервисы не в норме и ошибки в логе. Панель опрашивает раз в
    30 с и показывает баннер и счётчик на пункте «Состояние»."""

    def __init__(self, status: StatusSource, logs: LogSource) -> None:
        self._status = status
        self._logs = logs

    async def __call__(self, q: GetAlerts) -> list[Alert]:
        out = [
            Alert(level=s.state, source=s.name, text=s.note or "требует внимания")
            for s in await self._status.services()
            if s.state in ("warn", "critical")
        ]
        edge = datetime.now(UTC) - timedelta(minutes=q.window_min)
        errors = [r for r in self._logs.recent(level="ERROR", limit=200, q="") if r.at >= edge]
        if errors:
            last = max(errors, key=lambda r: r.at)
            out.append(
                Alert(
                    level="critical" if len(errors) >= 10 else "warn",
                    source="Лог приложения",
                    text=f"ошибок за {q.window_min} мин: {len(errors)}; последняя — {last.message[:160]}",
                    at=last.at,
                )
            )
        return sorted(out, key=lambda a: a.level != "critical")
