"""Очистка журнала аудита старше срока хранения (п. 6.2). Срок — не меньше 6 месяцев (183 дня) независимо от
настройки: требование ТЗ к хранению журналов. Сама очистка пишется в аудит."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from aiskra.modules.audit.application.ports.retention import AuditPurger, RetentionPolicy
from aiskra.shared.application import Clock, Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.security import Principal

MIN_RETENTION_DAYS = 183


@dataclass(frozen=True, kw_only=True)
class PurgeAudit(Command):
    actor: Principal | None  # None — запуск по расписанию или из CLI
    dry_run: bool = False
    meta: RequestMeta = field(default_factory=RequestMeta)


@dataclass(frozen=True)
class PurgeResult:
    retention_days: int
    before: str
    deleted: int
    dry_run: bool


class PurgeAuditHandler:
    def __init__(
        self, purger: AuditPurger, policy: RetentionPolicy, audit: AuditRecorder, uow: UnitOfWork, clock: Clock
    ) -> None:
        self._purger = purger
        self._policy = policy
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def __call__(self, cmd: PurgeAudit) -> PurgeResult:
        days = max(MIN_RETENTION_DAYS, await self._policy.retention_days())
        before = self._clock.now() - timedelta(days=days)
        if cmd.dry_run:
            n = await self._purger.count_older(before)
            return PurgeResult(retention_days=days, before=before.isoformat(), deleted=n, dry_run=True)
        try:
            n = await self._purger.delete_older(before)
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.AUDIT_PURGED,
                    actor=cmd.actor,
                    meta=cmd.meta,
                    object_type="audit",
                    description=f"срок хранения {days} дн.: удалено записей старше {before:%d.%m.%Y} — {n}",
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return PurgeResult(retention_days=days, before=before.isoformat(), deleted=n, dry_run=False)
