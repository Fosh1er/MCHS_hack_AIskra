"""Оповещения администратора о сбоях (п. 10.6): сервисы не в норме и свежие ошибки лога."""

from datetime import UTC, datetime, timedelta

from aiskra.modules.system.application.ports.admin import LogRecord, ServiceState
from aiskra.modules.system.application.queries.admin import GetAlerts, GetAlertsHandler


class Status:
    def __init__(self, items: list[ServiceState]) -> None:
        self.items = items

    async def services(self) -> list[ServiceState]:
        return self.items


class Logs:
    def __init__(self, items: list[LogRecord]) -> None:
        self.items = items

    def recent(self, *, level: str, limit: int, q: str) -> list[LogRecord]:
        assert level == "ERROR"
        return self.items


async def test_alerts_from_services_and_recent_errors() -> None:
    now = datetime.now(UTC)
    status = Status(
        [
            ServiceState("База данных", "ok"),
            ServiceState("Резервные копии", "warn", note="копий ещё нет"),
            ServiceState("ИИ-модели", "critical", note="модель недоступна"),
        ]
    )
    logs = Logs(
        [
            LogRecord(now - timedelta(minutes=5), "ERROR", "aiskra", "модель недоступна: 429"),
            LogRecord(now - timedelta(hours=3), "ERROR", "aiskra", "старая ошибка"),
        ]
    )
    alerts = await GetAlertsHandler(status, logs)(GetAlerts())
    assert alerts[0].source == "ИИ-модели"  # критичные — первыми
    assert {a.source for a in alerts} == {"ИИ-модели", "Резервные копии", "Лог приложения"}
    log_alert = next(a for a in alerts if a.source == "Лог приложения")
    assert "ошибок за 60 мин: 1" in log_alert.text and "429" in log_alert.text


async def test_no_alerts_when_all_ok() -> None:
    assert await GetAlertsHandler(Status([ServiceState("База данных", "ok")]), Logs([]))(GetAlerts()) == []
