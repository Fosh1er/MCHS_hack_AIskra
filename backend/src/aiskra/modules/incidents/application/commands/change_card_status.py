"""Команды статуса сохранённой карточки (docs/brief/03 §2.12, §3 п. 12):
- «отработана» (Alt+S) — автор;
- «Проверена» (Alt+Y) и «Вернуть на доработку» (Alt+N) — преподаватель в роли главного специалиста."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from aiskra.modules.incidents.application.commands._card import card_entry, load_card, persist
from aiskra.modules.incidents.application.ports.cards import CardRepository
from aiskra.shared.application import Clock, Command, UnitOfWork
from aiskra.shared.audit import AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.security import Principal


class StatusAction(StrEnum):
    WORKED = "worked"
    CHECKED = "checked"
    RETURNED = "returned"


_EVENTS = {
    StatusAction.WORKED: AuditEvent.CARD_WORKED,
    StatusAction.CHECKED: AuditEvent.CARD_CHECKED,
    StatusAction.RETURNED: AuditEvent.CARD_RETURNED,
}


@dataclass(frozen=True, kw_only=True)
class ChangeCardStatus(Command):
    actor: Principal
    card_id: UUID
    action: StatusAction
    comment: str = ""
    meta: RequestMeta = field(default_factory=RequestMeta)


class ChangeCardStatusHandler:
    """Права на действие проверяет API (`training.participate` или `cards.check`), здесь — правила переходов."""

    def __init__(self, cards: CardRepository, audit: AuditRecorder, uow: UnitOfWork, clock: Clock) -> None:
        self._cards = cards
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def __call__(self, cmd: ChangeCardStatus) -> str:
        by_author = cmd.action is StatusAction.WORKED
        card = await load_card(self._cards, cmd.card_id, cmd.actor, author_only=by_author)
        now = self._clock.now()
        if cmd.action is StatusAction.WORKED:
            card.mark_worked(now)
        elif cmd.action is StatusAction.CHECKED:
            card.mark_checked(cmd.actor.user_id, now)
        else:
            card.return_for_rework()
        entry = card_entry(_EVENTS[cmd.action], cmd.actor, card, cmd.meta, cmd.comment.strip()[:500])
        await persist(self._cards, self._audit, self._uow, card, entry)
        return card.status.value
