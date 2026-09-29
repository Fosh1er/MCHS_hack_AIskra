"""Резервное копирование (п. 5.2). Копия — логическая выгрузка рабочих данных (пользователи, группы, сценарии,
занятия, карточки, оценки, аудит, настройки) в сжатый JSON: одинаково работает на PostgreSQL и SQLite и не зависит
от версии pg_dump. Справочники в копию не входят — они восстанавливаются импортом из data/."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from aiskra.modules.system.application.ports.admin import BackupInfo, BackupStore, SettingsStore
from aiskra.shared.application import Command, Query
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import DomainError, NotFoundError
from aiskra.shared.security import Principal

RESTORE_CONFIRM = "ВОССТАНОВИТЬ"


@dataclass(frozen=True, kw_only=True)
class CreateBackup(Command):
    actor: Principal | None  # None — встроенный планировщик (п. 10.5)
    meta: RequestMeta = field(default_factory=RequestMeta)


@dataclass(frozen=True, kw_only=True)
class RestoreBackup(Command):
    actor: Principal
    name: str
    confirm: str
    meta: RequestMeta = field(default_factory=RequestMeta)


@dataclass(frozen=True, kw_only=True)
class ListBackups(Query):
    pass


class CreateBackupHandler:
    """Аудит пишется изолированно (своя транзакция): выгрузка читает БД, но ничего не меняет."""

    def __init__(self, store: BackupStore, settings: SettingsStore, audit: AuditRecorder) -> None:
        self._store = store
        self._settings = settings
        self._audit = audit

    async def __call__(self, cmd: CreateBackup) -> BackupInfo:
        info = await self._store.create()
        keep = int((await self._settings.get("backup") or {}).get("keep", 10))
        pruned = self._store.prune(keep)
        await self._audit.record(
            AuditEntry(
                event=AuditEvent.BACKUP_CREATED,
                actor=cmd.actor,
                meta=cmd.meta,
                object_type="backup",
                object_id=info.name,
                description=f"{info.name}: таблиц {info.tables}, строк {info.rows}"
                + (f"; удалено старых копий: {pruned}" if pruned else ""),
            )
        )
        return info


class RestoreBackupHandler:
    """Восстановление заменяет рабочие данные целиком и завершает все сессии. Аудит — после восстановления,
    иначе запись пропала бы вместе с заменённым журналом."""

    def __init__(self, store: BackupStore, audit: AuditRecorder) -> None:
        self._store = store
        self._audit = audit

    async def __call__(self, cmd: RestoreBackup) -> BackupInfo:
        if cmd.confirm != RESTORE_CONFIRM:
            raise DomainError(f"Для подтверждения введите «{RESTORE_CONFIRM}»", code="confirm_required")
        if cmd.name not in {b.name for b in self._store.list()}:
            raise NotFoundError("Копия не найдена", code="backup_not_found")
        info = await self._store.restore(cmd.name)
        await self._audit.record(
            AuditEntry(
                event=AuditEvent.BACKUP_RESTORED,
                actor=cmd.actor,
                meta=cmd.meta,
                object_type="backup",
                object_id=info.name,
                description=f"{info.name}: таблиц {info.tables}, строк {info.rows}",
            )
        )
        return info


class ListBackupsHandler:
    def __init__(self, store: BackupStore) -> None:
        self._store = store

    async def __call__(self, q: ListBackups) -> list[BackupInfo]:
        return self._store.list()


MSK = ZoneInfo("Europe/Moscow")


def backup_due(now: datetime, daily_hour: int, last: datetime | None) -> bool:
    """Пора ли ежедневной копии (п. 10.5): наступил час по МСК, а сегодня (МСК) копии ещё не было."""
    local = now.astimezone(MSK)
    if local.hour < daily_hour:
        return False
    return last is None or last.astimezone(MSK).date() < local.date()


class DailyBackupJob:
    """Встроенный ежедневный запуск резервного копирования вместо cron (п. 10.5): вызывается раз в минуту."""

    def __init__(self, store: BackupStore, settings: SettingsStore, audit: AuditRecorder) -> None:
        self._store, self._settings = store, settings
        self._create = CreateBackupHandler(store, settings, audit)

    async def tick(self, now: datetime) -> BackupInfo | None:
        cfg = await self._settings.get("backup") or {}
        if not int(cfg.get("auto", 1)):
            return None
        last = max((b.created_at for b in self._store.list()), default=None)
        if not backup_due(now, int(cfg.get("daily_hour", 3)), last):
            return None
        return await self._create(CreateBackup(actor=None))
