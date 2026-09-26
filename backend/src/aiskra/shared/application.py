"""CQRS-lite примитивы (ADR-0002).

Команда меняет состояние, запрос — только читает. Шин и медиаторов нет:
обработчик вызывается напрямую из API через DI-заглушку (см. aiskra.shared.di).
Базовые классы нужны для единообразия и читаемости: по типу сразу видно намерение.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


@dataclass(frozen=True, kw_only=True)
class Command:
    """Намерение изменить состояние системы. Неизменяемое, валидированное на входе API."""


@dataclass(frozen=True, kw_only=True)
class Query:
    """Запрос на чтение. Не меняет состояние и не трогает агрегаты."""


class UnitOfWork(Protocol):
    """Граница транзакции для команд. Реализация — SQLAlchemy-сессия (platform.db)."""

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class Clock(Protocol):
    """Источник времени. Порт нужен для таймеров, сроков сессий и детерминированных тестов."""

    def now(self) -> datetime:
        """Текущее время UTC (aware)."""
        ...


class SystemClock:
    """Реальное время."""

    def now(self) -> datetime:
        return datetime.now(UTC)
