"""Порты модуля incidents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from aiskra.modules.incidents.domain.incident import IncidentCard


class CardRepository(Protocol):
    async def add(self, card: IncidentCard) -> None:
        """Сохранить новую карточку; номер присваивается здесь (следующий свободный)."""
        ...

    async def get(self, card_id: UUID) -> IncidentCard | None: ...

    async def save(self, card: IncidentCard) -> None: ...


@dataclass(frozen=True, kw_only=True)
class CardServiceView:
    code: str
    short: str
    integrated: bool
    is_main: bool
    added_by: str
    status: str
    status_at: datetime | None


@dataclass(frozen=True, kw_only=True)
class CardView:
    id: UUID
    number: int
    status: str
    author_id: UUID | None
    author_name: str | None
    operator_number: str | None
    arm_number: str | None
    opened_at: datetime | None
    saved_at: datetime | None
    processing_ms: int | None
    data: dict[str, Any]
    services: list[CardServiceView]


class CardReader(Protocol):
    async def get(self, card_id: UUID) -> CardView | None: ...
