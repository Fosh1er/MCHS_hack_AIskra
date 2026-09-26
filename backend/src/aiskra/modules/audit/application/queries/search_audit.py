"""Запросы журнала аудита: поиск событий и каталог типов (раздел «Аудит» АРМ-112, `image114.png`).

Поиск повторяет оригинал: строка «Поиск события», флажки «по оператору» / «по карточке»,
«Тип события», период по датам и времени, 15 записей на странице.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from aiskra.modules.audit.application.ports.reader import AuditFilter, AuditReader
from aiskra.shared.application import Query
from aiskra.shared.audit import AUDIT_EVENT_TITLES, AuditEvent
from aiskra.shared.errors import DomainError

PAGE_SIZES = (15, 30, 50, 100)


@dataclass(frozen=True, kw_only=True)
class SearchAudit(Query):
    q: str = ""
    by_operator: bool = True
    by_card: bool = True
    event: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    page: int = 1
    page_size: int = 15


@dataclass(frozen=True, kw_only=True)
class AuditItem:
    id: int
    at: datetime
    card_number: int | None
    operator_number: str | None
    actor_name: str | None
    actor_login: str | None
    actor_role: str | None
    arm_number: str | None
    event: str
    event_title: str
    description: str | None
    ip: str | None


@dataclass(frozen=True, kw_only=True)
class AuditPage:
    items: list[AuditItem]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True, kw_only=True)
class EventType:
    code: str
    title: str


def event_title(code: str) -> str:
    try:
        return AUDIT_EVENT_TITLES[AuditEvent(code)]
    except ValueError:
        return code  # событие из более новой версии каталога


class SearchAuditHandler:
    def __init__(self, reader: AuditReader) -> None:
        self._reader = reader

    async def __call__(self, query: SearchAudit) -> AuditPage:
        if query.page_size not in PAGE_SIZES:
            raise DomainError(f"Записей на странице: одно из {PAGE_SIZES}", code="bad_page_size")
        if query.page < 1:
            raise DomainError("Номер страницы начинается с 1", code="bad_page")
        if query.date_from and query.date_to and query.date_from > query.date_to:
            raise DomainError("Начало периода позже конца", code="bad_period")
        if query.event and query.event not in AUDIT_EVENT_TITLES:
            raise DomainError(f"Неизвестный тип события: {query.event}", code="bad_event")
        rows, total = await self._reader.search(
            AuditFilter(
                q=query.q.strip(),
                by_operator=query.by_operator,
                by_card=query.by_card,
                event=query.event,
                date_from=query.date_from,
                date_to=query.date_to,
                limit=query.page_size,
                offset=(query.page - 1) * query.page_size,
            )
        )
        items = [
            AuditItem(
                id=r.id,
                at=r.at,
                card_number=r.card_number,
                operator_number=r.operator_number,
                actor_name=r.actor_name,
                actor_login=r.actor_login,
                actor_role=r.actor_role,
                arm_number=r.arm_number,
                event=r.event,
                event_title=event_title(r.event),
                description=r.description,
                ip=r.ip,
            )
            for r in rows
        ]
        return AuditPage(items=items, total=total, page=query.page, page_size=query.page_size)


@dataclass(frozen=True, kw_only=True)
class ListEventTypes(Query):
    pass


class ListEventTypesHandler:
    """Каталог событий для списка «Тип события». Источник — `aiskra.shared.audit`, без БД."""

    async def __call__(self, query: ListEventTypes) -> list[EventType]:
        return [EventType(code=e.value, title=t) for e, t in AUDIT_EVENT_TITLES.items()]
