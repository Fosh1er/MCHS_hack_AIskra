"""Порты модуля incidents."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from aiskra.modules.incidents.domain.incident import IncidentCard, Workout


class CardRepository(Protocol):
    async def add(self, card: IncidentCard) -> None:
        """Сохранить новую карточку; номер присваивается здесь (следующий свободный)."""
        ...

    async def get(self, card_id: UUID) -> IncidentCard | None: ...

    async def register(self, card: IncidentCard) -> None:
        """Первое сохранение: карточка + службы со статусом «Добавлена» (п. 1.1)."""
        ...

    async def save(self, card: IncidentCard) -> None:
        """Изменение сохранённой карточки (статус, ЧС/ЧП, дополнение). Службы и их история не трогаются."""
        ...

    async def add_workout(self, workout: Workout) -> None: ...


# ------------------------------------------------------------------ чтение


@dataclass(frozen=True, kw_only=True)
class StatusHistoryItem:
    status: str
    at: datetime | None
    operator: str | None
    comment: str | None
    order_no: str | None = None  # «Номер наряда» (ДДС, п. 2.2)


@dataclass(frozen=True, kw_only=True)
class CardServiceView:
    code: str
    short: str
    integrated: bool
    is_main: bool
    added_by: str
    status: str
    status_at: datetime | None
    history: list[StatusHistoryItem] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class WorkoutView:
    id: UUID
    at: datetime
    operator_number: str | None
    service_code: str | None
    target: str
    called_to: str
    phone: str
    receiver: str
    message: str


@dataclass(frozen=True, kw_only=True)
class IncidentTypeInfo:
    """«Класс.:» — итоговый тип классификатора (col11) и тип ЕКП (col12)."""

    code: str
    final_type: str | None
    ekp_type: str | None


@dataclass(frozen=True)
class ReworkNote:
    comment: str
    at: datetime | None
    by: str | None


@dataclass(frozen=True, kw_only=True)
class CardView:
    id: UUID
    number: int
    status: str  # хранимый статус
    display_status: str  # для журнала: + «not_notified», если есть служба без интеграции без отработки
    author_id: UUID | None
    author_name: str | None
    operator_number: str | None
    arm_number: str | None
    opened_at: datetime | None
    saved_at: datetime | None
    worked_at: datetime | None
    checked_at: datetime | None
    checked_by_name: str | None
    processing_ms: int | None
    is_emergency: bool
    is_incident: bool
    address_line: str | None  # «г. Москва, Новая Басманная улица, 6, к. 1, (ЦАО, Басманный)»
    data: dict[str, Any]
    services: list[CardServiceView]
    workouts: list[WorkoutView]
    incident_types: list[IncidentTypeInfo]
    rework: ReworkNote | None = None  # последний «Вернуть на доработку», пока карточка не отработана снова


@dataclass(frozen=True, kw_only=True)
class JournalFilter:
    q: str = ""
    statuses: list[str] = field(default_factory=list)  # display_status; пусто — все
    date_from: datetime | None = None
    date_to: datetime | None = None
    author_id: UUID | None = None  # None — все карточки (преподаватель)
    limit: int = 15
    offset: int = 0


@dataclass(frozen=True, kw_only=True)
class JournalRow:
    """Строка «Списка происшествий» (`image57`)."""

    id: UUID
    number: int
    display_status: str
    checked: bool
    is_emergency: bool
    is_incident: bool
    operator_number: str | None
    arm_number: str | None
    author_name: str | None
    channel: str | None
    registered_at: datetime | None
    card_types: list[str]
    empty_call: str | None  # no_contact | call_dropped
    has_victims: bool
    victims_count: int
    address_line: str | None
    description: str | None


class CardReader(Protocol):
    async def get(self, card_id: UUID) -> CardView | None: ...

    async def search(self, flt: JournalFilter) -> tuple[list[JournalRow], int]: ...
