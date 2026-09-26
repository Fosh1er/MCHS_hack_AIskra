"""SQL-реализация порта чтения справочников (запросы CQRS-lite)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.dictionaries.application.ports.reader import (
    CardTypeRow,
    DistrictRow,
    EnumValueRow,
    GroupRow,
    IncidentTypeRow,
    OkrugRow,
    RoutingCell,
    ServiceRow,
)
from aiskra.modules.dictionaries.domain.model import search_form
from aiskra.modules.dictionaries.infrastructure.models import (
    CardTypeModel,
    DistrictModel,
    EnumValueModel,
    IncidentGroupModel,
    IncidentTypeModel,
    OkrugModel,
    RoutingModel,
    ServiceColumnModel,
    ServiceModel,
)


def _type_row(t: IncidentTypeModel, group_title: str) -> IncidentTypeRow:
    return IncidentTypeRow(
        code=t.code,
        group_id=t.group_id,
        group_title=group_title,
        sign1=t.sign1,
        sign2=t.sign2,
        sign3=t.sign3,
        final_type=t.final_type,
        ekp_type=t.ekp_type,
        response_scenario=t.response_scenario,
        main_services=list(t.main_services or []),
        visible_to_112=t.visible_to_112,
        operator_hint=t.operator_hint,
    )


_TERRITORIAL_KINDS = ("district_dds", "prefecture_dds", "okrug_roads")


def _service_row(x: ServiceModel) -> ServiceRow:
    return ServiceRow(
        code=x.code,
        short=x.short_name,
        full=x.full_name,
        kind=x.kind,
        okrug=x.okrug_code,
        district=x.district_code,
        phone=x.phone,
        phone_synthetic=x.phone_synthetic,
        confirmed=x.confirmed,
        source=x.source,
        main_codes=list(x.main_codes or []),
        integrated=x.integrated,
    )


def _district_row(d: DistrictModel) -> DistrictRow:
    return DistrictRow(
        code=d.code, name=d.name, okrug=d.okrug_code, kind=d.kind, dds=d.dds_service_code, aliases=list(d.aliases or [])
    )


def _card_row(c: CardTypeModel) -> CardTypeRow:
    return CardTypeRow(
        code=c.code,
        title=c.title,
        kind=c.kind,
        group_id=c.group_id,
        sign1=list(c.sign1 or []),
        synonyms=list(c.synonyms or []),
        quick=c.quick,
        significant=c.significant,
    )


class SqlDictionaryReader:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def search_incident_types(
        self,
        *,
        terms: list[str],
        groups: list[int] | None,
        sign1: list[str] | None,
        visible_only: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[IncidentTypeRow], int]:
        cond: list[Any] = [IncidentTypeModel.active.is_(True)]
        cond += [IncidentTypeModel.search_text.contains(t) for t in terms]
        if groups:
            cond.append(IncidentTypeModel.group_id.in_(groups))
        if sign1:
            cond.append(IncidentTypeModel.sign1_key.in_([search_form(x) for x in sign1]))
        if visible_only:
            cond.append(IncidentTypeModel.visible_to_112.is_(True))
        where = and_(*cond)
        total = (await self._s.execute(select(func.count()).select_from(IncidentTypeModel).where(where))).scalar_one()
        stmt = (
            select(IncidentTypeModel, IncidentGroupModel.title)
            .join(IncidentGroupModel, IncidentGroupModel.id == IncidentTypeModel.group_id)
            .where(where)
            .order_by(IncidentTypeModel.group_id, IncidentTypeModel.code)
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._s.execute(stmt)).all()
        return [_type_row(t, g) for t, g in rows], int(total)

    async def get_incident_type(self, code: str) -> IncidentTypeRow | None:
        stmt = (
            select(IncidentTypeModel, IncidentGroupModel.title)
            .join(IncidentGroupModel, IncidentGroupModel.id == IncidentTypeModel.group_id)
            .where(IncidentTypeModel.code == code)
        )
        row = (await self._s.execute(stmt)).first()
        return _type_row(row[0], row[1]) if row else None

    async def get_routing(self, code: str) -> list[RoutingCell]:
        stmt = (
            select(RoutingModel, ServiceColumnModel, ServiceModel.short_name)
            .join(ServiceColumnModel, ServiceColumnModel.col == RoutingModel.col)
            .outerjoin(ServiceModel, ServiceModel.code == ServiceColumnModel.service_code)
            .where(RoutingModel.incident_type_code == code)
            .order_by(RoutingModel.col)
        )
        return [
            RoutingCell(
                col=c.col,
                service=c.service_code,
                service_short=short,
                recipient=c.recipient,
                flag=c.flag,
                base=c.base,
                audience=c.audience,
                delivery=r.delivery,
                service_type=r.service_type,
            )
            for r, c, short in (await self._s.execute(stmt)).all()
        ]

    async def list_card_types(self) -> list[CardTypeRow]:
        rows = (await self._s.execute(select(CardTypeModel).order_by(CardTypeModel.sort))).scalars().all()
        return [_card_row(c) for c in rows]

    async def get_card_type(self, code: str) -> CardTypeRow | None:
        c = await self._s.get(CardTypeModel, code)
        return _card_row(c) if c else None

    async def list_services(
        self, *, kinds: list[str] | None, okrug: str | None, terms: list[str], limit: int
    ) -> list[ServiceRow]:
        cond: list[Any] = [ServiceModel.active.is_(True)]
        cond += [ServiceModel.search_text.contains(t) for t in terms]
        if kinds:
            cond.append(ServiceModel.kind.in_(kinds))
        if okrug:
            cond.append(ServiceModel.okrug_code == okrug)
        stmt = select(ServiceModel).where(and_(*cond)).order_by(ServiceModel.kind, ServiceModel.short_name).limit(limit)
        return [_service_row(x) for x in (await self._s.execute(stmt)).scalars().all()]

    async def get_services(self, codes: list[str]) -> list[ServiceRow]:
        if not codes:
            return []
        stmt = select(ServiceModel).where(ServiceModel.code.in_(codes), ServiceModel.active.is_(True))
        return [_service_row(x) for x in (await self._s.execute(stmt)).scalars().all()]

    async def list_main_services(self) -> list[ServiceRow]:
        # коды главной службы есть только у служб верхнего уровня (~20 строк) — фильтр в Python переносим между СУБД
        stmt = select(ServiceModel).where(ServiceModel.active.is_(True), ServiceModel.kind.not_in(_TERRITORIAL_KINDS))
        return [_service_row(x) for x in (await self._s.execute(stmt)).scalars().all() if x.main_codes]

    async def get_district(self, code: str) -> DistrictRow | None:
        d = await self._s.get(DistrictModel, code)
        return _district_row(d) if d is not None and d.active else None

    async def list_groups(self) -> list[GroupRow]:
        rows = (await self._s.execute(select(IncidentGroupModel).order_by(IncidentGroupModel.id))).scalars().all()
        return [GroupRow(id=g.id, title=g.title) for g in rows]

    async def list_okrugs(self) -> list[OkrugRow]:
        rows = (await self._s.execute(select(OkrugModel))).scalars().all()
        return [OkrugRow(code=o.code, short=o.short, name=o.name, prefecture=o.prefecture_code) for o in rows]

    async def list_districts(self, *, okrug: str | None, terms: list[str]) -> list[DistrictRow]:
        cond: list[Any] = [DistrictModel.active.is_(True)]
        cond += [DistrictModel.search_text.contains(t) for t in terms]
        if okrug:
            cond.append(DistrictModel.okrug_code == okrug)
        rows = (await self._s.execute(select(DistrictModel).where(and_(*cond)).order_by(DistrictModel.name))).scalars()
        return [_district_row(d) for d in rows.all()]

    async def list_enum(self, domain: str) -> list[EnumValueRow]:
        stmt = select(EnumValueModel).where(EnumValueModel.domain == domain).order_by(EnumValueModel.sort)
        return [
            EnumValueRow(domain=e.domain, code=e.code, name=e.name, sort=e.sort, attrs=dict(e.attrs or {}))
            for e in (await self._s.execute(stmt)).scalars().all()
        ]

    async def list_enum_domains(self) -> list[str]:
        stmt = select(EnumValueModel.domain).distinct().order_by(EnumValueModel.domain)
        return list((await self._s.execute(stmt)).scalars().all())
