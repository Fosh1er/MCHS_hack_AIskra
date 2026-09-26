"""Команда: тумблеры ЧС / ЧП в просмотре карточки (`image59`, `image87`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from aiskra.modules.incidents.application.commands._card import card_entry, load_card, persist
from aiskra.modules.incidents.application.ports.cards import CardRepository
from aiskra.shared.application import Command, UnitOfWork
from aiskra.shared.audit import AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.security import Principal


@dataclass(frozen=True, kw_only=True)
class SetCardFlags(Command):
    actor: Principal
    card_id: UUID
    emergency: bool
    incident: bool
    meta: RequestMeta = field(default_factory=RequestMeta)


class SetCardFlagsHandler:
    def __init__(self, cards: CardRepository, audit: AuditRecorder, uow: UnitOfWork) -> None:
        self._cards = cards
        self._audit = audit
        self._uow = uow

    async def __call__(self, cmd: SetCardFlags) -> list[str]:
        card = await load_card(self._cards, cmd.card_id, cmd.actor)
        changed = card.set_flags(emergency=cmd.emergency, incident=cmd.incident)
        if changed:
            state = f"ЧС: {'да' if card.is_emergency else 'нет'}, ЧП: {'да' if card.is_incident else 'нет'}"
            await persist(
                self._cards,
                self._audit,
                self._uow,
                card,
                card_entry(AuditEvent.CARD_FLAGS, cmd.actor, card, cmd.meta, state),
            )
        return changed
