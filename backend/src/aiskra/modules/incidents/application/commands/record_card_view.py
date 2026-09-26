"""Команда: «Просмотр карточки» в аудите (как в разделе «Аудит» оригинала, `image114`).

Отдельная команда, а не побочный эффект запроса: запрос карточки повторяется при каждом обновлении экрана,
а в журнал аудита просмотр пишется один раз — когда оператор открыл карточку (ADR-0002)."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from aiskra.modules.incidents.application.commands._card import card_entry, load_card
from aiskra.modules.incidents.application.ports.cards import CardRepository
from aiskra.shared.application import Command, UnitOfWork
from aiskra.shared.audit import AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.security import Principal


@dataclass(frozen=True, kw_only=True)
class RecordCardView(Command):
    actor: Principal
    card_id: UUID
    meta: RequestMeta = field(default_factory=RequestMeta)


class RecordCardViewHandler:
    def __init__(self, cards: CardRepository, audit: AuditRecorder, uow: UnitOfWork) -> None:
        self._cards = cards
        self._audit = audit
        self._uow = uow

    async def __call__(self, cmd: RecordCardView) -> None:
        card = await load_card(self._cards, cmd.card_id, cmd.actor, author_only=False)
        await self._audit.record(card_entry(AuditEvent.CARD_VIEWED, cmd.actor, card, cmd.meta))
        await self._uow.commit()
