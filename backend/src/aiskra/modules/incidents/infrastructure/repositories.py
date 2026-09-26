"""SQL-хранилище карточек 112: сущность ↔ incident_cards + card_services + card_service_statuses."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.incidents.domain.card import IncidentCardData
from aiskra.modules.incidents.domain.incident import AddedBy, CardService, CardStatus, IncidentCard
from aiskra.modules.incidents.infrastructure.models import (
    CardServiceModel,
    CardServiceStatusModel,
    IncidentCardModel,
)
from aiskra.platform.types import as_utc

NUMBER_BASE = 36_900_000  # восьмизначные номера, как на стенде 2026 («Происшествие 36814851»)
_NUMBER_ATTEMPTS = 5


class SqlCardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, card: IncidentCard) -> None:
        """Следующий номер = максимум + 1. Две карточки одновременно — повтор с новым номером (уникальный индекс)."""
        for _ in range(_NUMBER_ATTEMPTS):
            current = (await self._s.execute(select(func.max(IncidentCardModel.number)))).scalar_one_or_none()
            card.number = max(current or 0, NUMBER_BASE) + 1
            try:
                async with self._s.begin_nested():
                    self._s.add(_new_row(card))
                return
            except IntegrityError:
                continue
        raise RuntimeError("Не удалось выделить номер карточки")

    async def get(self, card_id: UUID) -> IncidentCard | None:
        row = await self._s.get(IncidentCardModel, card_id)
        if row is None:
            return None
        services = (
            await self._s.execute(select(CardServiceModel).where(CardServiceModel.card_id == card_id))
        ).scalars()
        opened_at = as_utc(row.opened_at)
        assert opened_at is not None and row.author_id is not None
        return IncidentCard(
            id=row.id,
            number=row.number,
            author_id=row.author_id,
            opened_at=opened_at,
            operator_number=row.operator_number,
            arm_number=row.arm_number,
            status=CardStatus(row.status),
            data=IncidentCardData.from_dict(row.payload) if row.payload else IncidentCardData(),
            services=[
                CardService(
                    code=s.service_code, is_main=s.is_main, added_by=AddedBy(s.added_by), service_type=s.service_type
                )
                for s in services
            ],
            saved_at=as_utc(row.saved_at),
        )

    async def save(self, card: IncidentCard) -> None:
        row = await self._s.get(IncidentCardModel, card.id)
        if row is None:
            raise LookupError(f"Карточка {card.id} не найдена при сохранении")
        _fill(row, card)
        await self._s.execute(delete(CardServiceModel).where(CardServiceModel.card_id == card.id))
        for s in card.services:
            self._s.add(
                CardServiceModel(
                    card_id=card.id,
                    service_code=s.code,
                    is_main=s.is_main,
                    added_by=s.added_by.value,
                    service_type=s.service_type,
                    current_status="added",
                )
            )
            self._s.add(
                CardServiceStatusModel(
                    card_id=card.id, service_code=s.code, status="added", actor_id=card.author_id, at=card.saved_at
                )
            )
        await self._s.flush()


def _new_row(card: IncidentCard) -> IncidentCardModel:
    row = IncidentCardModel(id=card.id, number=card.number, author_id=card.author_id, origin="student")
    _fill(row, card)
    return row


def _fill(row: IncidentCardModel, card: IncidentCard) -> None:
    d = card.data
    row.number = card.number
    row.status = card.status.value
    row.operator_number = card.operator_number
    row.arm_number = card.arm_number
    row.channel = d.channel
    row.card_type_codes = list(d.card_types)
    row.incident_type_codes = list(d.incident_types)
    row.okrug_code = d.address.okrug
    row.district_code = d.address.district
    row.address_text = address_line(d)
    row.description = d.description or None
    row.has_victims = d.victims.has
    row.victims_count = d.victims.count
    row.payload = d.to_dict()
    row.opened_at = card.opened_at
    row.saved_at = card.saved_at
    row.processing_ms = card.processing_ms


def address_line(d: IncidentCardData) -> str | None:
    """Адрес одной строкой, как в сохранённой карточке: «Москва, Новая Басманная улица, 6, к. 1, кв. 5»."""
    a = d.address
    parts = [
        a.city or a.region,
        a.street,
        a.house,
        f"к. {a.building}" if a.building else "",
        f"с. {a.structure}" if a.structure else "",
        f"кв. {a.flat}" if a.flat else "",
    ]
    line = ", ".join(p for p in parts if p)
    return line if (a.street or a.house or a.descriptive) else (a.descriptive or None)
