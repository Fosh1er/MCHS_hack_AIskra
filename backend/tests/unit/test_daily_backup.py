"""Встроенное ежедневное резервное копирование (п. 10.5): час по МСК, одна копия в сутки, выключатель."""

from datetime import UTC, datetime
from typing import Any

from aiskra.modules.system.application.commands.backups import DailyBackupJob, backup_due
from aiskra.modules.system.application.ports.admin import BackupInfo


def utc(h: int, m: int = 0, d: int = 29) -> datetime:
    return datetime(2026, 9, d, h, m, tzinfo=UTC)


def test_due_after_hour_once_per_moscow_day() -> None:
    assert not backup_due(utc(23, d=28), 3, None)  # 02:00 МСК 29.09 — ещё рано
    assert backup_due(utc(0, 30), 3, None)  # 03:30 МСК
    assert not backup_due(utc(5), 3, utc(0, 31))  # сегодня (МСК) уже была
    assert backup_due(utc(1, d=30), 3, utc(0, 31))  # следующие сутки
    assert backup_due(utc(12), 3, utc(20, d=27))  # пропустили ночь (стенд был выключен) — копия днём


class Store:
    def __init__(self) -> None:
        self.items: list[BackupInfo] = []

    async def create(self) -> BackupInfo:
        info = BackupInfo(name=f"b{len(self.items)}", size_bytes=1, created_at=utc(0, 40), tables=1, rows=1)
        self.items.insert(0, info)
        return info

    def list(self) -> list[BackupInfo]:
        return self.items

    def prune(self, keep: int) -> int:
        return 0

    async def restore(self, name: str) -> BackupInfo:
        raise NotImplementedError


class Settings:
    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg

    async def get(self, key: str) -> dict[str, Any] | None:
        return self.cfg if key == "backup" else None


class Audit:
    def __init__(self) -> None:
        self.entries: list[Any] = []

    async def record(self, entry: Any) -> None:
        self.entries.append(entry)


async def test_job_creates_one_copy_per_day_and_respects_switch() -> None:
    store, audit = Store(), Audit()
    job = DailyBackupJob(store, Settings({"auto": 1, "daily_hour": 3, "keep": 10}), audit)  # type: ignore[arg-type]
    assert await job.tick(utc(23, d=28)) is None
    assert (await job.tick(utc(0, 35))) is not None
    assert await job.tick(utc(0, 36)) is None  # в те же сутки — не повторяет
    assert len(store.items) == 1 and audit.entries[0].actor is None  # в аудите — система, не пользователь
    off = DailyBackupJob(Store(), Settings({"auto": 0, "daily_hour": 3}), Audit())  # type: ignore[arg-type]
    assert await off.tick(utc(12)) is None
