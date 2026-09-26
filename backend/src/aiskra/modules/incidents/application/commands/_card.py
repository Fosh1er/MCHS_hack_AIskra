"""Общее для команд над сохранённой карточкой: загрузка, проверка автора, «сохранить + аудит + коммит»."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from aiskra.modules.incidents.application.ports.cards import CardRepository
from aiskra.modules.incidents.domain.incident import IncidentCard
from aiskra.shared.application import UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import NotFoundError
from aiskra.shared.security import Permission, Principal


async def load_card(
    cards: CardRepository, card_id: UUID, actor: Principal, *, author_only: bool = True
) -> IncidentCard:
    """Чужая карточка для обучающегося «не существует» (404), преподаватель видит любую (`results.read_all`)."""
    card = await cards.get(card_id)
    visible = card is not None and (
        card.author_id == actor.user_id or (not author_only and actor.can(Permission.RESULTS_READ_ALL))
    )
    if card is None or not visible:
        raise NotFoundError("Карточка не найдена", code="card_not_found")
    return card


def card_entry(
    event: AuditEvent,
    actor: Principal,
    card: IncidentCard,
    meta: RequestMeta,
    description: str = "",
    data: dict[str, Any] | None = None,
) -> AuditEntry:
    return AuditEntry(
        event=event,
        actor=actor,
        card_number=card.number,
        description=description,
        object_type="incident_card",
        object_id=str(card.id),
        meta=meta,
        data=data or {},
    )


async def persist(
    cards: CardRepository, audit: AuditRecorder, uow: UnitOfWork, card: IncidentCard, entry: AuditEntry
) -> None:
    try:
        await cards.save(card)
        await audit.record(entry)
        await uow.commit()
    except Exception:
        await uow.rollback()
        raise
