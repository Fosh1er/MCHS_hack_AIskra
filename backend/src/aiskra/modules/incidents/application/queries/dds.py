"""Запросы АРМ ДДС (п. 2.1, 2.2): реестр карточек службы и карточка глазами ДДС."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from aiskra.modules.incidents.application.ports.cards import CardReader, CardView
from aiskra.modules.incidents.application.ports.dds import (
    BrigadeOption,
    DdsFilter,
    DdsJournalRow,
    DdsReader,
    DdsRepository,
)
from aiskra.modules.incidents.domain.dds import ServiceStatus, next_statuses
from aiskra.shared.application import Query
from aiskra.shared.errors import DomainError, NotFoundError, PermissionDeniedError
from aiskra.shared.security import Permission, Principal

PAGE_SIZES = (10, 15, 30, 50, 100)


def ensure_dds_reader(actor: Principal) -> None:
    """Реестр ДДС видят обучающийся (работает за службу) и преподаватель (контроль)."""
    if not (actor.can(Permission.TRAINING_PARTICIPATE) or actor.can(Permission.RESULTS_READ_ALL)):
        raise PermissionDeniedError("АРМ ДДС доступен обучающимся и преподавателям")


@dataclass(frozen=True, kw_only=True)
class SearchDdsJournal(Query):
    actor: Principal
    service_code: str
    q: str = ""
    statuses: list[str] = field(default_factory=list)
    page: int = 1
    page_size: int = 10


@dataclass(frozen=True, kw_only=True)
class DdsJournalPage:
    items: list[DdsJournalRow]
    total: int
    page: int
    page_size: int


class SearchDdsJournalHandler:
    def __init__(self, reader: DdsReader) -> None:
        self._reader = reader

    async def __call__(self, query: SearchDdsJournal) -> DdsJournalPage:
        ensure_dds_reader(query.actor)
        if query.page_size not in PAGE_SIZES or query.page < 1:
            raise DomainError(f"Записей на странице: одно из {PAGE_SIZES}, страница с 1", code="bad_page")
        known = {s.value for s in ServiceStatus}
        unknown = set(query.statuses) - known
        if unknown:
            raise DomainError(f"Неизвестный статус службы: {', '.join(sorted(unknown))}", code="bad_status_filter")
        rows, total = await self._reader.search(
            DdsFilter(
                service_code=query.service_code,
                q=query.q.strip(),
                statuses=list(query.statuses),
                limit=query.page_size,
                offset=(query.page - 1) * query.page_size,
            )
        )
        return DdsJournalPage(items=rows, total=total, page=query.page, page_size=query.page_size)


@dataclass(frozen=True, kw_only=True)
class GetDdsCard(Query):
    actor: Principal
    card_id: UUID
    service_code: str


@dataclass(frozen=True, kw_only=True)
class DdsCardView:
    """Карточка 112 глазами ДДС: содержимое (только чтение), своя служба и доступные ей статусы."""

    card: CardView
    service_code: str
    service_status: str
    next_statuses: list[str]


class GetDdsCardHandler:
    def __init__(self, reader: CardReader) -> None:
        self._reader = reader

    async def __call__(self, query: GetDdsCard) -> DdsCardView:
        ensure_dds_reader(query.actor)
        card = await self._reader.get(query.card_id)
        own = next((s for s in card.services if s.code == query.service_code), None) if card else None
        if card is None or own is None or card.status == "draft":
            raise NotFoundError("Карточка не поступала в эту службу", code="dds_card_not_found")
        can_act = query.actor.can(Permission.TRAINING_PARTICIPATE)
        return DdsCardView(
            card=card,
            service_code=own.code,
            service_status=own.status,
            next_statuses=[s.value for s in next_statuses(ServiceStatus(own.status))] if can_act else [],
        )


@dataclass(frozen=True, kw_only=True)
class ListDdsBrigades(Query):
    """Справочник сил своей службы для выбора в карточке ДДС (п. 5.5): занятые на других карточках помечены."""

    actor: Principal
    service_code: str
    card_id: UUID | None = None  # бригады этой карточки не считаются занятыми


class ListDdsBrigadesHandler:
    def __init__(self, repo: DdsRepository) -> None:
        self._repo = repo

    async def __call__(self, query: ListDdsBrigades) -> list[BrigadeOption]:
        ensure_dds_reader(query.actor)
        return await self._repo.brigades(query.service_code, exclude_card=query.card_id)
