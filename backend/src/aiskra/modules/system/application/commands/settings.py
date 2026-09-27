"""Настройки системы (п. 5.2): тайминг и пороги занятия по умолчанию, параметры резервного копирования.
Хранятся в `system_settings`; без записи действуют значения по умолчанию. Модели ИИ правятся в config/ai.yaml
(секреты и адреса — вне БД, ADR-0003), здесь — только просмотр."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aiskra.modules.system.application.ports.admin import SettingsStore
from aiskra.shared.application import Command, Query, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import DomainError
from aiskra.shared.security import Principal

# ключ → (значение по умолчанию, минимум, максимум)
LIMITS: dict[str, dict[str, tuple[float, float, float]]] = {
    "session_defaults": {
        "norm_112": (75, 5, 3600),
        "norm_dds": (30, 5, 3600),
        "threshold": (70, 0, 100),
        "difficulty": (2, 1, 5),
        "call_interval_s": (40, 5, 3600),
        "feed_interval_s": (45, 5, 3600),
        "max_waiting": (3, 1, 10),
    },
    "backup": {
        "keep": (10, 1, 100),  # сколько копий хранить
    },
    "audit": {
        "retention_days": (365, 183, 3650),  # срок хранения журнала аудита; не меньше 6 месяцев (п. 6.2)
    },
}


def defaults() -> dict[str, dict[str, float]]:
    return {k: {f: v[0] for f, v in fields.items()} for k, fields in LIMITS.items()}


def merged(key: str, stored: dict[str, Any] | None) -> dict[str, float]:
    base = {f: v[0] for f, v in LIMITS[key].items()}
    return {**base, **{k: v for k, v in (stored or {}).items() if k in base}}


@dataclass(frozen=True, kw_only=True)
class GetSettings(Query):
    pass


class GetSettingsHandler:
    def __init__(self, store: SettingsStore) -> None:
        self._store = store

    async def __call__(self, q: GetSettings) -> dict[str, dict[str, float]]:
        return {key: merged(key, await self._store.get(key)) for key in LIMITS}


@dataclass(frozen=True, kw_only=True)
class UpdateSettings(Command):
    actor: Principal
    key: str
    values: dict[str, float]
    meta: RequestMeta = field(default_factory=RequestMeta)


class UpdateSettingsHandler:
    def __init__(self, store: SettingsStore, audit: AuditRecorder, uow: UnitOfWork) -> None:
        self._store = store
        self._audit = audit
        self._uow = uow

    async def __call__(self, cmd: UpdateSettings) -> dict[str, float]:
        limits = LIMITS.get(cmd.key)
        if limits is None:
            raise DomainError(f"Неизвестный раздел настроек: {cmd.key}", code="bad_settings_key")
        for f, v in cmd.values.items():
            if f not in limits:
                raise DomainError(f"Неизвестный параметр: {f}", code="bad_setting")
            _, lo, hi = limits[f]
            if not lo <= float(v) <= hi:
                raise DomainError(f"Параметр {f}: от {lo:g} до {hi:g}", code="bad_setting")
        before = merged(cmd.key, await self._store.get(cmd.key))
        after = {**before, **{k: float(v) for k, v in cmd.values.items()}}
        changes = [f"{k}: {before[k]:g} → {after[k]:g}" for k in after if before[k] != after[k]]
        try:
            await self._store.put(cmd.key, after, cmd.actor.user_id)
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.SETTINGS_CHANGED,
                    actor=cmd.actor,
                    meta=cmd.meta,
                    description=f"{cmd.key}: " + ("; ".join(changes) or "без изменений"),
                    object_type="settings",
                    object_id=cmd.key,
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return after
