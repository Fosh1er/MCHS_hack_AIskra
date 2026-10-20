"""Запросы АРМ ДДС (п. 2.1, 2.2): реестр карточек службы и карточка глазами ДДС."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from aiskra.modules.incidents.application.ports.cards import CardReader, CardView
from aiskra.modules.incidents.application.ports.dds import (
    BrigadeOption,
    DdsFilter,
    DdsJournalRow,
    DdsPosts,
    DdsReader,
    DdsRepository,
    DdsServiceState,
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


async def dds_scope(posts: DdsPosts, actor: Principal, service_code: str) -> list[UUID | None] | None:
    """Чьи карточки службы видит пользователь (ТЗ 2.7, 2.8). Преподаватель — все занятия и карточки вне занятий
    (None). Обучающийся-диспетчер на идущем занятии — только карточки занятий, где он диспетчер этой службы; другая
    служба во время занятия — 403. Вне занятия (свободная практика, демо-стенд) — любая служба, но только карточки,
    не привязанные ни к какому занятию (`[None]`): карточки чужих занятий код службы в адресе не открывает."""
    ensure_dds_reader(actor)
    if actor.can(Permission.RESULTS_READ_ALL):
        return None
    running = await posts.running(actor.user_id)
    sessions: list[UUID | None] = [p.session_id for p in running if p.service_code == service_code]
    if sessions:
        return sessions
    if running:
        raise PermissionDeniedError("На занятии АРМ ДДС открыт только для вашей службы", code="dds_not_assigned")
    return [None]


def ensure_in_scope(state: DdsServiceState | None, sessions: list[UUID | None] | None) -> DdsServiceState:
    """Карточка, не направленная в службу, черновик 112 или карточка другого занятия для ДДС «не существует»."""
    if state is None or state.card_status == "draft" or (sessions is not None and state.session_id not in sessions):
        raise NotFoundError("Карточка не поступала в эту службу", code="dds_card_not_found")
    return state


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
    def __init__(self, reader: DdsReader, posts: DdsPosts) -> None:
        self._reader = reader
        self._posts = posts

    async def __call__(self, query: SearchDdsJournal) -> DdsJournalPage:
        sessions = await dds_scope(self._posts, query.actor, query.service_code)
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
                session_ids=sessions,
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
    def __init__(self, reader: CardReader, repo: DdsRepository, posts: DdsPosts) -> None:
        self._reader = reader
        self._repo = repo
        self._posts = posts

    async def __call__(self, query: GetDdsCard) -> DdsCardView:
        sessions = await dds_scope(self._posts, query.actor, query.service_code)
        ensure_in_scope(await self._repo.state(query.card_id, query.service_code), sessions)
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
    def __init__(self, repo: DdsRepository, posts: DdsPosts) -> None:
        self._repo = repo
        self._posts = posts

    async def __call__(self, query: ListDdsBrigades) -> list[BrigadeOption]:
        await dds_scope(self._posts, query.actor, query.service_code)
        return await self._repo.brigades(query.service_code, exclude_card=query.card_id)
