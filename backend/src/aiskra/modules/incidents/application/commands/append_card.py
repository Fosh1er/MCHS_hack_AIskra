"""Команда «дополнение» (Shift+F2): только пустые поля, дописать описание, пострадавшие."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from aiskra.modules.incidents.application.commands._card import card_entry, load_card, persist
from aiskra.modules.incidents.application.ports.cards import CardRepository
from aiskra.modules.incidents.domain.incident import Appendix
from aiskra.shared.application import Command, UnitOfWork
from aiskra.shared.audit import AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.security import Principal


@dataclass(frozen=True, kw_only=True)
class AppendCard(Command):
    actor: Principal
    card_id: UUID
    appendix: Appendix
    meta: RequestMeta = field(default_factory=RequestMeta)


class AppendCardHandler:
    def __init__(self, cards: CardRepository, audit: AuditRecorder, uow: UnitOfWork) -> None:
        self._cards = cards
        self._audit = audit
        self._uow = uow

    async def __call__(self, cmd: AppendCard) -> list[str]:
        card = await load_card(self._cards, cmd.card_id, cmd.actor)
        changed = card.append(cmd.appendix)
        if changed:
            entry = card_entry(AuditEvent.CARD_APPENDED, cmd.actor, card, cmd.meta, "дополнены: " + ", ".join(changed))
            await persist(self._cards, self._audit, self._uow, card, entry)
        return changed
