"""SQL-чтение карточки для показа.

Имена служб и автора берутся из таблиц справочников и пользователей через лёгкие `table()`-описания:
модуль не импортирует ORM-модели других модулей (независимость модулей, ADR-0001), а связь
на уровне БД уже задана внешними ключами card_services → dict_services и incident_cards → users.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import column, select, table
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.incidents.application.ports.cards import CardServiceView, CardView
from aiskra.modules.incidents.infrastructure.models import (
    CardServiceModel,
    CardServiceStatusModel,
    IncidentCardModel,
)
from aiskra.platform.types import as_utc

_services = table("dict_services", column("code"), column("short_name"), column("integrated"))
_users = table("users", column("id"), column("full_name"))


class SqlCardReader:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, card_id: UUID) -> CardView | None:
        found = (
            await self._s.execute(
                select(IncidentCardModel, _users.c.full_name)
                .outerjoin(_users, _users.c.id == IncidentCardModel.author_id)
                .where(IncidentCardModel.id == card_id)
            )
        ).first()
        if found is None:
            return None
        card, author_name = found
        rows = (
            await self._s.execute(
                select(CardServiceModel, _services.c.short_name, _services.c.integrated)
                .outerjoin(_services, _services.c.code == CardServiceModel.service_code)
                .where(CardServiceModel.card_id == card_id)
            )
        ).all()
        last_status_at = {
            code: as_utc(at)
            for code, at in (
                await self._s.execute(
                    select(CardServiceStatusModel.service_code, CardServiceStatusModel.at)
                    .where(CardServiceStatusModel.card_id == card_id)
                    .order_by(CardServiceStatusModel.id)
                )
            ).all()
        }
        return CardView(
            id=card.id,
            number=card.number,
            status=card.status,
            author_id=card.author_id,
            author_name=author_name,
            operator_number=card.operator_number,
            arm_number=card.arm_number,
            opened_at=as_utc(card.opened_at),
            saved_at=as_utc(card.saved_at),
            processing_ms=card.processing_ms,
            data=dict(card.payload or {}),
            services=[
                CardServiceView(
                    code=s.service_code,
                    short=short or s.service_code,
                    integrated=integrated is not False,
                    is_main=s.is_main,
                    added_by=s.added_by,
                    status=s.current_status,
                    status_at=last_status_at.get(s.service_code),
                )
                for s, short, integrated in rows
            ],
        )
