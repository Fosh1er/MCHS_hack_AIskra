"""Базовые строительные блоки домена. Чистый Python: без фреймворков, БД и pydantic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


def new_id() -> UUID:
    return uuid4()


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(eq=False, kw_only=True)
class Entity:
    """Сущность: равенство по идентификатору, а не по полям."""

    id: UUID = field(default_factory=new_id)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, type(self)) and other.id == self.id

    def __hash__(self) -> int:
        return hash(self.id)


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """Факт, произошедший в домене. В MVP события не публикуются шиной —
    обработчик команды явно вызывает нужные реакции (см. ADR-0002)."""

    occurred_at: datetime = field(default_factory=utcnow)
