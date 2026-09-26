"""Команда: сохранить карточку 112 — «оповестить и сохранить карточку» (Alt+S, окно `image56.png`).

Службы присылает клиент: автоподбор показан оператору на панели, он мог убрать или добавить службу вручную.
Каждая служба получает статус «Добавлена» — дальше статусы ведёт ДДС (п. 2.x).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from aiskra.modules.incidents.application.ports.cards import CardRepository
from aiskra.modules.incidents.domain.card import IncidentCardData
from aiskra.modules.incidents.domain.incident import CardService, CardStatus
from aiskra.shared.application import Clock, Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import DomainError, NotFoundError
from aiskra.shared.security import Principal


@dataclass(frozen=True, kw_only=True)
class SaveCard(Command):
    actor: Principal
    card_id: UUID
    data: dict[str, Any]
    services: list[CardService]
    meta: RequestMeta = field(default_factory=RequestMeta)


@dataclass(frozen=True, kw_only=True)
class CardSaved:
    id: UUID
    number: int
    status: CardStatus
    saved_at: datetime
    processing_ms: int
    services: list[CardService]


class SaveCardHandler:
    def __init__(self, cards: CardRepository, audit: AuditRecorder, uow: UnitOfWork, clock: Clock) -> None:
        self._cards = cards
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def __call__(self, cmd: SaveCard) -> CardSaved:
        card = await self._cards.get(cmd.card_id)
        if card is None or card.author_id != cmd.actor.user_id:  # чужая карточка не «существует»
            raise NotFoundError("Карточка не найдена", code="card_not_found")
        try:
            data = IncidentCardData.from_dict(cmd.data)
        except TypeError as exc:
            raise DomainError(f"Некорректная структура карточки: {exc}", code="bad_card") from exc
        card.save(data, cmd.services, self._clock.now())
        assert card.saved_at is not None and card.processing_ms is not None
        try:
            await self._cards.register(card)
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.CARD_SAVED,
                    actor=cmd.actor,
                    card_number=card.number,
                    description=_describe(card.data, card.services, card.processing_ms),
                    object_type="incident_card",
                    object_id=str(card.id),
                    meta=cmd.meta,
                    data={"incident_types": card.data.incident_types, "services": [s.code for s in card.services]},
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return CardSaved(
            id=card.id,
            number=card.number,
            status=card.status,
            saved_at=card.saved_at,
            processing_ms=card.processing_ms,
            services=card.services,
        )


def _describe(data: IncidentCardData, services: list[CardService], processing_ms: int) -> str:
    seconds = processing_ms // 1000
    timer = f"{seconds // 60:02d}:{seconds % 60:02d}"
    if data.flags.no_contact:
        return f"Нет контакта, карточка пустая ({timer})"
    if data.flags.call_dropped:
        return f"Срыв звонка, карточка пустая ({timer})"
    return f"Типы: {', '.join(data.card_types)}; служб: {len(services)}; таймер {timer}"
