"""Порты панели администратора (п. 5.2): настройки, резервные копии, логи, состояние сервисов."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID


class SettingsStore(Protocol):
    async def get(self, key: str) -> dict[str, Any] | None: ...

    async def put(self, key: str, value: dict[str, Any], actor_id: UUID) -> None: ...


@dataclass(frozen=True)
class BackupInfo:
    name: str
    size_bytes: int
    created_at: datetime
    tables: int = 0
    rows: int = 0


class BackupStore(Protocol):
    async def create(self) -> BackupInfo: ...

    def list(self) -> list[BackupInfo]: ...

    def prune(self, keep: int) -> int: ...

    async def restore(self, name: str) -> BackupInfo: ...


@dataclass(frozen=True)
class LogRecord:
    at: datetime
    level: str
    logger: str
    message: str


class LogSource(Protocol):
    def recent(self, *, level: str, limit: int, q: str) -> list[LogRecord]: ...


@dataclass(frozen=True)
class ServiceState:
    name: str
    state: str  # ok | warn | critical | off
    metrics: list[tuple[str, str]] = field(default_factory=list)
    note: str = ""


class StatusSource(Protocol):
    async def services(self) -> list[ServiceState]: ...
