"""Порт чтения журнала аудита."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, kw_only=True)
class AuditFilter:
    q: str = ""
    by_operator: bool = True  # искать в ФИО, логине и номере оператора
    by_card: bool = True  # искать по номеру карточки
    event: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    limit: int = 15
    offset: int = 0


@dataclass(frozen=True, kw_only=True)
class AuditRow:
    id: int
    at: datetime
    card_number: int | None
    operator_number: str | None
    actor_name: str | None
    actor_login: str | None
    actor_role: str | None
    arm_number: str | None
    event: str
    description: str | None
    ip: str | None


class AuditReader(Protocol):
    async def search(self, flt: AuditFilter) -> tuple[list[AuditRow], int]: ...
