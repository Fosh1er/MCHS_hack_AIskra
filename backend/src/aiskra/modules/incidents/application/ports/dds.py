"""Порты АРМ ДДС (п. 2.1, 2.2): статус своей службы по карточке и реестр карточек службы."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class DdsServiceState:
    card_id: UUID
    card_number: int
    card_status: str
    service_code: str
    service_short: str
    current_status: str
    paused_ms: int | None = None  # п. 5.3: пауза таймера решения на подсказки
    pause_started_at: datetime | None = None
    brigades: list[str] = field(default_factory=list)  # п. 5.5: силы службы, работающие по карточке


@dataclass(frozen=True, kw_only=True)
class BrigadeOption:
    """Бригада справочника службы (п. 5.5) и где она сейчас работает."""

    code: str
    call_sign: str
    name: str
    kind: str
    crew: int
    busy_card_id: UUID | None = None  # другая незакрытая карточка службы, по которой бригада направлена
    busy_card_number: int | None = None


class DdsRepository(Protocol):
    async def state(self, card_id: UUID, service_code: str) -> DdsServiceState | None: ...

    async def timer_states(self, service_code: str, *, paused: bool) -> list[DdsServiceState]:
        """Карточки службы для паузы таймера (п. 5.3): `paused=False` — ждут решения, `True` — сейчас на паузе."""
        ...

    async def set_pause(
        self, card_id: UUID, service_code: str, *, paused_ms: int | None, pause_started_at: datetime | None
    ) -> None: ...

    async def brigades(self, service_code: str, *, exclude_card: UUID | None = None) -> list[BrigadeOption]:
        """Активные бригады службы; занятость — по незакрытым карточкам службы, кроме `exclude_card`."""
        ...

    async def set_status(
        self,
        card_id: UUID,
        service_code: str,
        status: str,
        *,
        order_no: str | None,
        comment: str | None,
        actor_id: UUID,
        at: datetime,
        brigades: list[str] | None = None,
    ) -> None:
        """Новый текущий статус службы + строка истории (card_service_statuses). `brigades` — новый состав сил
        (None — не менять)."""
        ...


@dataclass(frozen=True, kw_only=True)
class DdsFilter:
    service_code: str
    q: str = ""
    statuses: list[str] = field(default_factory=list)  # статусы службы; пусто — все
    limit: int = 15
    offset: int = 0


@dataclass(frozen=True, kw_only=True)
class DdsJournalRow:
    """Строка реестра ДДС «Список происшествий» (dds/image3–5)."""

    id: UUID
    number: int
    is_emergency: bool
    is_incident: bool
    operator_number: str | None
    arm_number: str | None
    channel: str | None
    registered_at: datetime | None
    card_types: list[str]
    empty_call: str | None
    has_victims: bool
    victims_count: int
    address_line: str | None
    description: str | None
    author_name: str | None
    service_status: str
    service_status_at: datetime | None
    added_at: datetime | None  # когда карточка поступила в службу — от этого времени идёт таймер ожидания
    paused_ms: int = 0  # п. 5.3: пауза таймера ожидания на подсказки — не входит во время реакции
    pause_started_at: datetime | None = None  # пауза идёт сейчас — таймер стоит


class DdsReader(Protocol):
    async def search(self, flt: DdsFilter) -> tuple[list[DdsJournalRow], int]: ...
