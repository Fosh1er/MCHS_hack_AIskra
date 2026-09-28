"""SQL-адаптеры АРМ ДДС (п. 2.1, 2.2): статус службы по карточке и реестр карточек службы."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, column, func, select, table, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.incidents.application.ports.dds import DdsFilter, DdsJournalRow, DdsServiceState
from aiskra.modules.incidents.domain.dds import WAITING
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
                select(C.number, C.status, CS.current_status, _services.c.short_name, CS.paused_ms, CS.pause_started_at)
                .select_from(CS)
                .join(C, C.id == CS.card_id)
                .outerjoin(_services, _services.c.code == CS.service_code)
                .where(CS.card_id == card_id, CS.service_code == service_code)
            )
        ).first()
        if found is None:
            return None
        number, card_status, current, short, paused_ms, pause_started_at = found
        return DdsServiceState(
            card_id=card_id,
            card_number=number,
            card_status=card_status,
            service_code=service_code,
            service_short=short or service_code,
            current_status=current,
            paused_ms=paused_ms,
            pause_started_at=as_utc(pause_started_at),
        )

    async def timer_states(self, service_code: str, *, paused: bool) -> list[DdsServiceState]:
        cond = CS.pause_started_at.is_not(None) if paused else CS.current_status.in_(WAITING)
        rows = await self._s.execute(
            select(
                CS.card_id,
                C.number,
                C.status,
                CS.current_status,
                CS.paused_ms,
                CS.pause_started_at,
                _services.c.short_name,
            )
            .join(C, C.id == CS.card_id)
            .outerjoin(_services, _services.c.code == CS.service_code)
            .where(CS.service_code == service_code, cond)
        )
        return [
            DdsServiceState(
                card_id=cid,
                card_number=number,
                card_status=card_status,
                service_code=service_code,
                service_short=short or service_code,
                current_status=current,
                paused_ms=ms,
                pause_started_at=as_utc(started),
            )
            for cid, number, card_status, current, ms, started, short in rows.all()
        ]

    async def set_pause(
        self, card_id: UUID, service_code: str, *, paused_ms: int | None, pause_started_at: datetime | None
    ) -> None:
        await self._s.execute(
            update(CS)
            .where(CS.card_id == card_id, CS.service_code == service_code)
            .values(paused_ms=paused_ms, pause_started_at=pause_started_at)
        )
        await self._s.flush()

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
        """Три шага (6.1): подсчёт без подзапросов; страница id по индексу saved_at; полные строки и «время
        статуса» — только для строк страницы. Один общий запрос считал подзапрос времени по всем карточкам службы."""
        # строки служб есть только у сохранённых карточек (создаются при сохранении) — черновики не попадают
        conditions: list[ColumnElement[bool]] = [CS.service_code == flt.service_code]
        if flt.statuses:
            conditions.append(CS.current_status.in_(flt.statuses))
        scope = select(CS.card_id).where(*conditions)
        if flt.q:
            scope = scope.join(C, C.id == CS.card_id).where(C.search_key.like(f"%{search_key(flt.q)}%"))
        total = int((await self._s.execute(select(func.count()).select_from(scope.subquery()))).scalar_one())
        page_ids = (
            (
                await self._s.execute(
                    scope.order_by(CS.card_saved_at.desc(), CS.card_number.desc()).limit(flt.limit).offset(flt.offset)
                )
            )
            .scalars()
            .all()
        )
        if not page_ids:
            return [], total
        last_at = (
            select(func.max(H.at))
            .where(H.card_id == CS.card_id, H.service_code == CS.service_code)
            .correlate(CS)
            .scalar_subquery()
        )
        rows = (
            await self._s.execute(
                select(
                    C,
                    CS.current_status,
                    last_at.label("status_at"),
                    CS.paused_ms,
                    CS.pause_started_at,
                    _users.c.full_name,
                    _okrugs.c.short,
                    _districts.c.name,
                )
                .select_from(CS)
                .join(C, C.id == CS.card_id)
                .outerjoin(_users, _users.c.id == C.author_id)
                .outerjoin(_okrugs, _okrugs.c.code == C.okrug_code)
                .outerjoin(_districts, _districts.c.code == C.district_code)
                # пара (карточка, служба) = первичный ключ строки службы: поиск по ключу, а не перебор службы
                .where(tuple_(CS.card_id, CS.service_code).in_([(i, flt.service_code) for i in page_ids]))
                .order_by(CS.card_saved_at.desc(), CS.card_number.desc())
            )
        ).all()
        return [self._row(*r) for r in rows], total

    @staticmethod
    def _row(
        c: C,
        status: str,
        status_at: Any,
        paused_ms: int | None,
        pause_started_at: datetime | None,
        author: str | None,
        okrug: str | None,
        district: str | None,
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
            paused_ms=paused_ms or 0,
            pause_started_at=as_utc(pause_started_at),
        )
