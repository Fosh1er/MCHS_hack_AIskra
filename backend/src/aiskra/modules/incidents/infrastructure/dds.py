"""SQL-адаптеры АРМ ДДС (п. 2.1, 2.2): статус службы по карточке и реестр карточек службы."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, column, func, select, table, update
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.incidents.application.ports.dds import DdsFilter, DdsJournalRow, DdsServiceState
from aiskra.modules.incidents.infrastructure.models import CardServiceModel as CS
from aiskra.modules.incidents.infrastructure.models import CardServiceStatusModel as H
from aiskra.modules.incidents.infrastructure.models import IncidentCardModel as C
from aiskra.modules.incidents.infrastructure.reader import _address
from aiskra.platform.types import as_utc
from aiskra.shared.text import search_key

_services = table("dict_services", column("code"), column("short_name"))
_users = table("users", column("id"), column("full_name"))
_okrugs = table("dict_okrugs", column("code"), column("short"))
_districts = table("dict_districts", column("code"), column("name"))


class SqlDdsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def state(self, card_id: UUID, service_code: str) -> DdsServiceState | None:
        found = (
            await self._s.execute(
                select(C.number, C.status, CS.current_status, _services.c.short_name)
                .select_from(CS)
                .join(C, C.id == CS.card_id)
                .outerjoin(_services, _services.c.code == CS.service_code)
                .where(CS.card_id == card_id, CS.service_code == service_code)
            )
        ).first()
        if found is None:
            return None
        number, card_status, current, short = found
        return DdsServiceState(
            card_id=card_id,
            card_number=number,
            card_status=card_status,
            service_code=service_code,
            service_short=short or service_code,
            current_status=current,
        )

    async def set_status(
        self,
        card_id: UUID,
        service_code: str,
        status: str,
        *,
        order_no: str | None,
        comment: str | None,
        actor_id: UUID,
        at: datetime,
    ) -> None:
        await self._s.execute(
            update(CS).where(CS.card_id == card_id, CS.service_code == service_code).values(current_status=status)
        )
        self._s.add(
            H(
                card_id=card_id,
                service_code=service_code,
                status=status,
                order_no=order_no,
                comment=comment,
                actor_id=actor_id,
                at=at,
            )
        )
        await self._s.flush()


class SqlDdsReader:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def search(self, flt: DdsFilter) -> tuple[list[DdsJournalRow], int]:
        last_at = (
            select(func.max(H.at))
            .where(H.card_id == CS.card_id, H.service_code == CS.service_code)
            .correlate(CS)
            .scalar_subquery()
        )
        conditions: list[ColumnElement[bool]] = [CS.service_code == flt.service_code, C.status != "draft"]
        if flt.q:
            conditions.append(C.search_key.like(f"%{search_key(flt.q)}%"))
        if flt.statuses:
            conditions.append(CS.current_status.in_(flt.statuses))
        base = (
            select(
                C, CS.current_status, last_at.label("status_at"), _users.c.full_name, _okrugs.c.short, _districts.c.name
            )
            .select_from(CS)
            .join(C, C.id == CS.card_id)
            .outerjoin(_users, _users.c.id == C.author_id)
            .outerjoin(_okrugs, _okrugs.c.code == C.okrug_code)
            .outerjoin(_districts, _districts.c.code == C.district_code)
            .where(*conditions)
        )
        total = int((await self._s.execute(select(func.count()).select_from(base.subquery()))).scalar_one())
        rows = (
            await self._s.execute(
                base.order_by(func.coalesce(C.saved_at, C.opened_at).desc(), C.number.desc())
                .limit(flt.limit)
                .offset(flt.offset)
            )
        ).all()
        return [self._row(*r) for r in rows], total

    @staticmethod
    def _row(
        c: C, status: str, status_at: Any, author: str | None, okrug: str | None, district: str | None
    ) -> DdsJournalRow:
        flags: dict[str, Any] = (c.payload or {}).get("flags") or {}
        empty = "no_contact" if flags.get("no_contact") else "call_dropped" if flags.get("call_dropped") else None
        return DdsJournalRow(
            id=c.id,
            number=c.number,
            is_emergency=c.is_emergency,
            is_incident=c.is_incident,
            operator_number=c.operator_number,
            arm_number=c.arm_number,
            channel=c.channel,
            registered_at=as_utc(c.opened_at) or as_utc(c.created_at),
            card_types=list(c.card_type_codes or []),
            empty_call=empty,
            has_victims=c.has_victims,
            victims_count=c.victims_count,
            address_line=_address(c.address_text, okrug, district),
            description=c.description,
            author_name=author,
            service_status=status,
            service_status_at=as_utc(status_at) if isinstance(status_at, datetime) else None,
            added_at=as_utc(c.saved_at),
        )
