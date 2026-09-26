"""Запрос: карточка для показа (после сохранения, перезагрузки страницы; журнал — п. 1.3).

Обучающийся видит только свои карточки (ТЗ 2.7), преподаватель — любые (право `results.read_all`).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from aiskra.modules.incidents.application.ports.cards import CardReader, CardView
from aiskra.shared.application import Query
from aiskra.shared.errors import NotFoundError
from aiskra.shared.security import Permission, Principal


@dataclass(frozen=True, kw_only=True)
class GetCard(Query):
    actor: Principal
    card_id: UUID


class GetCardHandler:
    def __init__(self, reader: CardReader) -> None:
        self._reader = reader

    async def __call__(self, query: GetCard) -> CardView:
        view = await self._reader.get(query.card_id)
        visible = view is not None and (
            view.author_id == query.actor.user_id or query.actor.can(Permission.RESULTS_READ_ALL)
        )
        if view is None or not visible:
            raise NotFoundError("Карточка не найдена", code="card_not_found")  # чужая карточка не «существует»
        return view
