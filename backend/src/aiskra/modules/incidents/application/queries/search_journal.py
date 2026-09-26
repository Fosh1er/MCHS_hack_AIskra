"""Запрос: «Список происшествий» — журнал карточек 112 (`image57`, `image113`).

Обучающийся видит только свои карточки (ТЗ 2.7), преподаватель — все (право `results.read_all`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from aiskra.modules.incidents.application.ports.cards import CardReader, JournalFilter, JournalRow
from aiskra.shared.application import Query
from aiskra.shared.errors import DomainError, PermissionDeniedError
from aiskra.shared.security import Permission, Principal

PAGE_SIZES = (15, 30, 50, 100)
DISPLAY_STATUSES = ("draft", "registered", "not_notified", "worked", "checked", "completed")


@dataclass(frozen=True, kw_only=True)
class SearchJournal(Query):
    actor: Principal
    q: str = ""
    statuses: list[str] = field(default_factory=list)
    date_from: datetime | None = None
    date_to: datetime | None = None
    page: int = 1
    page_size: int = 15


@dataclass(frozen=True, kw_only=True)
class JournalPage:
    items: list[JournalRow]
    total: int
    page: int
    page_size: int


class SearchJournalHandler:
    def __init__(self, reader: CardReader) -> None:
        self._reader = reader

    async def __call__(self, query: SearchJournal) -> JournalPage:
        actor = query.actor
        if actor.can(Permission.RESULTS_READ_ALL):
            author = None
        elif actor.can(Permission.TRAINING_PARTICIPATE):
            author = actor.user_id
        else:
            raise PermissionDeniedError("Журнал карточек доступен обучающимся и преподавателям")
        if query.page_size not in PAGE_SIZES:
            raise DomainError(f"Записей на странице: одно из {PAGE_SIZES}", code="bad_page_size")
        if query.page < 1:
            raise DomainError("Номер страницы начинается с 1", code="bad_page")
        unknown = set(query.statuses) - set(DISPLAY_STATUSES)
        if unknown:
            raise DomainError(f"Неизвестный статус: {', '.join(sorted(unknown))}", code="bad_status_filter")
        rows, total = await self._reader.search(
            JournalFilter(
                q=query.q.strip(),
                statuses=list(query.statuses),
                date_from=query.date_from,
                date_to=query.date_to,
                author_id=author,
                limit=query.page_size,
                offset=(query.page - 1) * query.page_size,
            )
        )
        return JournalPage(items=rows, total=total, page=query.page, page_size=query.page_size)
