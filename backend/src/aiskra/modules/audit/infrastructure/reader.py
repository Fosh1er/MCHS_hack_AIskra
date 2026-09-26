"""SQL-поиск по журналу аудита. Индексы: `at`, `event`, `card_number`, `actor_login`, `actor_id`."""

from __future__ import annotations

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.audit.application.ports.reader import AuditFilter, AuditRow
from aiskra.modules.audit.infrastructure.models import AuditLogModel as A
from aiskra.platform.types import as_utc
from aiskra.shared.text import search_key


class SqlAuditReader:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def search(self, flt: AuditFilter) -> tuple[list[AuditRow], int]:
        conditions: list[ColumnElement[bool]] = []
        if flt.q:
            pattern = f"%{search_key(flt.q)}%"
            text_fields: list[ColumnElement[bool]] = [A.description_key.like(pattern)]
            if flt.by_operator:
                text_fields += [A.actor_key.like(pattern), A.operator_number == flt.q]
            if flt.by_card and flt.q.isdigit():
                text_fields.append(A.card_number == int(flt.q))
            conditions.append(or_(*text_fields))
        if flt.event:
            conditions.append(A.event == flt.event)
        if flt.date_from:
            conditions.append(A.at >= flt.date_from)
        if flt.date_to:
            conditions.append(A.at <= flt.date_to)

        total = int((await self._s.execute(select(func.count()).select_from(A).where(*conditions))).scalar_one())
        rows = (
            await self._s.execute(
                select(A).where(*conditions).order_by(A.at.desc(), A.id.desc()).limit(flt.limit).offset(flt.offset)
            )
        ).scalars()
        items = [
            AuditRow(
                id=r.id,
                at=as_utc(r.at) or r.at,
                card_number=r.card_number,
                operator_number=r.operator_number,
                actor_name=r.actor_name,
                actor_login=r.actor_login,
                actor_role=r.actor_role,
                arm_number=r.arm_number,
                event=r.event,
                description=r.description,
                ip=r.ip,
            )
            for r in rows
        ]
        return items, total
