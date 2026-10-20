"""Связи карточек и поиск повторных обращений (п. 1.6, ТЗ 4.6): «Есть карточка с заявителем по этому номеру»
(`image62`), «совпадение» по адресу (`image61`), окно связей «главная / подчинённая» (`image65–68`)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import ColumnElement, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.incidents.application.ports.cards import JournalRow, MatchQuery
from aiskra.modules.incidents.domain.links import address_key, phone_key
from aiskra.modules.incidents.infrastructure.models import IncidentCardModel as C
from aiskra.modules.incidents.infrastructure.reader import SqlCardReader

CANDIDATES = 300  # сколько недавних карточек сверять: журнал за сутки учебного класса


class SqlCardLinks:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def main_of(self, card_id: UUID) -> UUID | None:
        return (await self._s.execute(select(C.main_card_id).where(C.id == card_id))).scalar_one_or_none()

    async def set_main(self, card_id: UUID, main_id: UUID | None) -> None:
        await self._s.execute(update(C).where(C.id == card_id).values(main_card_id=main_id))

    async def subordinates(self, main_id: UUID) -> list[UUID]:
        return list((await self._s.execute(select(C.id).where(C.main_card_id == main_id))).scalars())

    async def rows(self, ids: list[UUID], author_id: UUID | None = None) -> list[JournalRow]:
        if not ids:
            return []
        conditions: list[ColumnElement[bool]] = [C.id.in_(ids)]
        if author_id is not None:
            conditions.append(C.author_id == author_id)
        return await SqlCardReader(self._s).rows_where(*conditions, limit=len(ids))

    async def matches(self, q: MatchQuery) -> list[JournalRow]:
        phones = {k for p in q.phones if (k := phone_key(p))}
        place = address_key(q.street, q.house)
        if not phones and not place:
            return []
        since = datetime.now(UTC) - timedelta(hours=q.hours)
        conditions: list[ColumnElement[bool]] = [C.status != "draft", C.saved_at >= since]
        if q.exclude is not None:
            conditions.append(C.id != q.exclude)
        if q.author_id is not None:
            conditions.append(C.author_id == q.author_id)
        found = (
            await self._s.execute(
                select(C.id, C.payload).where(*conditions).order_by(C.saved_at.desc()).limit(CANDIDATES)
            )
        ).all()
        by: dict[UUID, str] = {}
        for card_id, payload in found:
            p = payload or {}
            own = {k for v in (p.get("phones") or {}).values() if isinstance(v, str) and (k := phone_key(v))}
            a = p.get("address") or {}
            if phones & own:
                by[card_id] = "phone"
            elif place and address_key(a.get("street"), a.get("house")) == place:
                by[card_id] = "address"
            if len(by) >= q.limit:
                break
        rows = await self.rows(list(by))
        return [replace(r, match=by[r.id]) for r in rows]
