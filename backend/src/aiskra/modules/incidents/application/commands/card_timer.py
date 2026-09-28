"""Команда: пауза таймера черновика карточки 112 на время подсказок по экрану (п. 5.3).

Новый обучающийся при первом открытии карточки проходит подсказки по её полям; это время не должно идти в норматив
заполнения. Пауза одна на карточку и не дольше MAX_TIMER_PAUSE; её длительность пишется в журнал аудита, чтобы
преподаватель видел, откуда разница между часами и временем заполнения.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from aiskra.modules.incidents.application.commands._card import card_entry, load_card, persist
from aiskra.modules.incidents.application.ports.cards import CardRepository
from aiskra.shared.application import Clock, Command, UnitOfWork
from aiskra.shared.audit import AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.security import Principal


@dataclass(frozen=True, kw_only=True)
class SetCardTimerPaused(Command):
    actor: Principal
    card_id: UUID
    paused: bool
    meta: RequestMeta = field(default_factory=RequestMeta)


class SetCardTimerPausedHandler:
    def __init__(self, cards: CardRepository, audit: AuditRecorder, uow: UnitOfWork, clock: Clock) -> None:
        self._cards = cards
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def __call__(self, cmd: SetCardTimerPaused) -> int:
        """Возвращает, сколько всего таймер карточки стоял на паузе, мс."""
        card = await load_card(self._cards, cmd.card_id, cmd.actor)
        now = self._clock.now()
        if cmd.paused:
            card.pause_timer(now)
            try:
                await self._cards.save(card)
                await self._uow.commit()
            except Exception:
                await self._uow.rollback()
                raise
            return card.paused_ms or 0
        was_paused = card.pause_started_at is not None
        paused_ms = card.resume_timer(now)
        if was_paused:
            seconds = paused_ms // 1000
            entry = card_entry(
                AuditEvent.CARD_TIMER_PAUSED,
                cmd.actor,
                card,
                cmd.meta,
                f"таймер стоял {seconds} с — подсказки по карточке",
                {"paused_ms": paused_ms},
            )
            await persist(self._cards, self._audit, self._uow, card, entry)
        return paused_ms
