"""Команды: привязать карточку к главной и отвязать (п. 1.6, ТЗ 4.6 — повторные обращения, `image62`, `image65`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from aiskra.modules.incidents.application.commands._card import card_entry, load_card
from aiskra.modules.incidents.application.ports.cards import CardLinks, CardRepository
from aiskra.modules.incidents.domain.incident import CardStatus
from aiskra.modules.incidents.domain.links import link_target
from aiskra.shared.application import Command, UnitOfWork
from aiskra.shared.audit import AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import DomainError
from aiskra.shared.security import Principal


@dataclass(frozen=True, kw_only=True)
class LinkCard(Command):
    """`main_id` — главная карточка; None — отвязать. Привязывать можно и черновик: баннер «Есть карточка с
    заявителем по этому номеру» появляется, пока оператор заполняет новую карточку."""

    actor: Principal
    card_id: UUID
    main_id: UUID | None
    meta: RequestMeta = field(default_factory=RequestMeta)


class LinkCardHandler:
    def __init__(self, cards: CardRepository, links: CardLinks, audit: AuditRecorder, uow: UnitOfWork) -> None:
        self._cards = cards
        self._links = links
        self._audit = audit
        self._uow = uow

    async def __call__(self, cmd: LinkCard) -> UUID | None:
        card = await load_card(self._cards, cmd.card_id, cmd.actor, author_only=False)
        if cmd.main_id is None:
            before = await self._links.main_of(card.id)
            if before is None:
                return None
            await self._links.set_main(card.id, None)
            main = await self._cards.get(before)
            entry = card_entry(
                AuditEvent.CARD_UNLINKED, cmd.actor, card, cmd.meta, f"от карточки {main.number if main else '—'}"
            )
            target = None
        else:
            main = await load_card(self._cards, cmd.main_id, cmd.actor, author_only=False)
            if await self._links.subordinates(card.id):
                raise DomainError(
                    "У карточки есть подчинённые — сначала отвяжите их или привяжите их к новой главной",
                    code="link_has_subordinates",
                )
            target = link_target(card.id, main.id, await self._links.main_of(main.id))
            root = main if target == main.id else await self._cards.get(target)
            if root is None or root.status is CardStatus.DRAFT:
                raise DomainError("Привязать можно только к сохранённой карточке", code="link_draft")
            if target == await self._links.main_of(card.id):
                return target  # повтор запроса
            await self._links.set_main(card.id, target)
            entry = card_entry(
                AuditEvent.CARD_LINKED,
                cmd.actor,
                card,
                cmd.meta,
                f"к главной карточке {root.number}",
                {"main_card_id": str(target)},
            )
        try:
            await self._audit.record(entry)
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return target
