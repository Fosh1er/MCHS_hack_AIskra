"""Команда: отработка — запись о звонке в службу после сохранения карточки (`image70`, `image87`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from aiskra.modules.incidents.application.commands._card import card_entry, load_card
from aiskra.modules.incidents.application.ports.cards import CardRepository
from aiskra.modules.incidents.domain.incident import CardStatus, Workout
from aiskra.shared.application import Clock, Command, UnitOfWork
from aiskra.shared.audit import AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import DomainError
from aiskra.shared.security import Principal


@dataclass(frozen=True, kw_only=True)
class AddWorkout(Command):
    actor: Principal
    card_id: UUID
    service_code: str | None = None
    target: str = ""
    called_to: str = ""
    phone: str = ""
    receiver: str = ""
    message: str = ""
    meta: RequestMeta = field(default_factory=RequestMeta)


class AddWorkoutHandler:
    def __init__(self, cards: CardRepository, audit: AuditRecorder, uow: UnitOfWork, clock: Clock) -> None:
        self._cards = cards
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def __call__(self, cmd: AddWorkout) -> UUID:
        card = await load_card(self._cards, cmd.card_id, cmd.actor)
        if card.status not in (CardStatus.REGISTERED, CardStatus.WORKED):
            raise DomainError(
                "Отработки добавляются к зарегистрированной или отработанной карточке", code="bad_card_status"
            )
        workout = Workout(
            card_id=card.id,
            author_id=cmd.actor.user_id,
            at=self._clock.now(),
            operator_number=cmd.actor.operator_number,
            service_code=cmd.service_code or None,
            target=cmd.target.strip(),
            called_to=cmd.called_to.strip(),
            phone=cmd.phone.strip(),
            receiver=cmd.receiver.strip(),
            message=cmd.message.strip(),
        )
        try:
            await self._cards.add_workout(workout)
            await self._audit.record(
                card_entry(
                    AuditEvent.WORKOUT_ADDED,
                    cmd.actor,
                    card,
                    cmd.meta,
                    f"{workout.target or workout.service_code}: {workout.message[:200]}",
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return workout.id
