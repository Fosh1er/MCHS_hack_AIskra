"""Команда: открыть новую карточку 112 (Insert или «Принять» входящий вызов — п. 1.4).

Номер присваивается сразу, как в АРМ: «Происшествие 36814851». Время открытия запускает таймер.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from aiskra.modules.incidents.application.ports.cards import CardRepository
from aiskra.modules.incidents.domain.card import IncidentCardData, Phones
from aiskra.modules.incidents.domain.incident import IncidentCard
from aiskra.shared.application import Clock, Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.security import Principal


@dataclass(frozen=True, kw_only=True)
class OpenCard(Command):
    actor: Principal
    aon: str = ""  # номер из телефонии; при ручном создании пусто
    channel: str | None = None
    meta: RequestMeta = field(default_factory=RequestMeta)


@dataclass(frozen=True, kw_only=True)
class CardOpened:
    id: UUID
    number: int
    opened_at: datetime


class OpenCardHandler:
    def __init__(self, cards: CardRepository, audit: AuditRecorder, uow: UnitOfWork, clock: Clock) -> None:
        self._cards = cards
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def __call__(self, cmd: OpenCard) -> CardOpened:
        card = IncidentCard(
            author_id=cmd.actor.user_id,
            opened_at=self._clock.now(),
            operator_number=cmd.actor.operator_number,
            arm_number=cmd.actor.arm_number,
            data=IncidentCardData(phones=Phones(aon=cmd.aon.strip()), channel=cmd.channel),
        )
        try:
            await self._cards.add(card)
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.CARD_CREATED,
                    actor=cmd.actor,
                    card_number=card.number,
                    description="входящий вызов" if card.data.phones.aon else "создана вручную",
                    object_type="incident_card",
                    object_id=str(card.id),
                    meta=cmd.meta,
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return CardOpened(id=card.id, number=card.number, opened_at=card.opened_at)
