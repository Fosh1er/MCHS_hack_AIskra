"""Запросы повторных обращений (п. 1.6, ТЗ 4.6): совпадения по телефону и адресу, окно связей карточки."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from aiskra.modules.incidents.application.commands._card import load_card
from aiskra.modules.incidents.application.ports.cards import CardLinks, CardRepository, JournalRow, MatchQuery
from aiskra.shared.application import Query
from aiskra.shared.security import Permission, Principal


@dataclass(frozen=True, kw_only=True)
class FindMatches(Query):
    """Обучающийся видит только свои карточки (как в журнале), преподаватель — все."""

    actor: Principal
    phones: list[str] = field(default_factory=list)
    street: str = ""
    house: str = ""
    exclude: UUID | None = None


class FindMatchesHandler:
    def __init__(self, links: CardLinks) -> None:
        self._links = links

    async def __call__(self, q: FindMatches) -> list[JournalRow]:
        own = None if q.actor.can(Permission.RESULTS_READ_ALL) else q.actor.user_id
        return await self._links.matches(
            MatchQuery(phones=q.phones, street=q.street, house=q.house, exclude=q.exclude, author_id=own)
        )


@dataclass(frozen=True, kw_only=True)
class GetLinks(Query):
    actor: Principal
    card_id: UUID


@dataclass(frozen=True)
class LinksView:
    main_id: UUID | None  # главная группы связей; None — связей нет
    rows: list[JournalRow]  # главная первой, затем подчинённые


class GetLinksHandler:
    def __init__(self, cards: CardRepository, links: CardLinks) -> None:
        self._cards = cards
        self._links = links

    async def __call__(self, q: GetLinks) -> LinksView:
        card = await load_card(self._cards, q.card_id, q.actor, author_only=False)
        main = await self._links.main_of(card.id) or card.id
        subs = await self._links.subordinates(main)
        if not subs:
            return LinksView(main_id=None, rows=[])
        own = None if q.actor.can(Permission.RESULTS_READ_ALL) else q.actor.user_id
        rows = await self._links.rows([main, *subs], own)
        rows.sort(key=lambda r: (r.id != main, r.number))
        return LinksView(main_id=main, rows=rows)
