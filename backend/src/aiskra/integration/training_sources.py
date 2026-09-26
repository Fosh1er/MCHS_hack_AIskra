"""Порты модуля training поверх dictionaries (факты для генерации сценариев) и incidents (карточка для звонков ДДС)."""

from __future__ import annotations

import random
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.dictionaries.application.queries.resolve_services import ResolveServices, ResolveServicesHandler
from aiskra.modules.dictionaries.domain.model import search_form
from aiskra.modules.dictionaries.infrastructure.models import (
    AddressModel,
    CardTypeModel,
    DistrictModel,
    IncidentGroupModel,
    IncidentTypeModel,
    StreetModel,
)
from aiskra.modules.dictionaries.infrastructure.reader import SqlDictionaryReader
from aiskra.modules.incidents.domain.dds import TITLES, ServiceStatus
from aiskra.modules.incidents.infrastructure.models import IncidentCardModel
from aiskra.modules.incidents.infrastructure.reader import SqlCardReader
from aiskra.modules.training.application.ports.scenarios import DdsCallContext
from aiskra.modules.training.domain.scenario import AddressFacts, IncidentFacts, ServiceFacts
from aiskra.shared.errors import DomainError

# Адрес на случай, если адресный справочник (п. 1.2) ещё не загружен
FALLBACK_ADDRESS = AddressFacts(
    street="Новая Басманная улица",
    house="13",
    building="",
    structure="",
    district="basmannyy",
    district_name="Басманный",
    okrug="CAO",
    lat=55.7697,
    lon=37.6558,
)


class DictionaryScenarioFacts:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session
        self._reader = SqlDictionaryReader(session)

    async def pick_incident(self, rng: random.Random, groups: list[int] | None) -> IncidentFacts:
        card_types = (
            (
                await self._s.execute(
                    select(CardTypeModel).where(CardTypeModel.kind == "incident", CardTypeModel.group_id.is_not(None))
                )
            )
            .scalars()
            .all()
        )
        by_group: dict[int, list[CardTypeModel]] = {}
        for c in card_types:
            assert c.group_id is not None
            by_group.setdefault(c.group_id, []).append(c)
        allowed = [g for g in by_group if not groups or g in groups]
        if not allowed:
            raise DomainError("Нет типов «Что случилось?» для выбранных групп", code="no_incident_types")
        stmt = (
            select(IncidentTypeModel, IncidentGroupModel.title)
            .join(IncidentGroupModel, IncidentGroupModel.id == IncidentTypeModel.group_id)
            .where(
                IncidentTypeModel.active.is_(True),
                IncidentTypeModel.visible_to_112.is_(True),
                IncidentTypeModel.group_id.in_(allowed),
                IncidentTypeModel.sign1.is_not(None),
            )
        )
        rows = (await self._s.execute(stmt)).all()
        if not rows:
            raise DomainError("Классификатор не загружен: выполните import-dictionaries", code="no_incident_types")
        ct: CardTypeModel | None = None
        for _ in range(20):
            t, group_title = rng.choice(rows)
            key = search_form(t.sign1 or "")
            ct = next(
                (x for x in by_group[t.group_id] if not x.sign1 or key in {search_form(s) for s in x.sign1}),
                None,
            )
            if ct is not None:
                break
        if ct is None:
            raise DomainError("Не удалось подобрать тип «Что случилось?»", code="no_incident_types")
        flags = sorted({c.flag for c in await self._reader.get_routing(t.code) if c.flag and c.audience == "card"})
        return IncidentFacts(
            code=t.code,
            group_id=t.group_id,
            group_title=group_title,
            card_type=ct.code,
            card_type_title=ct.title,
            sign1=t.sign1,
            sign2=t.sign2,
            sign3=t.sign3,
            final_type=t.final_type,
            flags=flags,
        )

    async def pick_address(self, rng: random.Random) -> AddressFacts:
        total = (await self._s.execute(select(func.count()).select_from(AddressModel))).scalar_one()
        if not total:
            return FALLBACK_ADDRESS
        row = (
            await self._s.execute(
                select(AddressModel, StreetModel.name, DistrictModel.name, DistrictModel.okrug_code)
                .join(StreetModel, StreetModel.id == AddressModel.street_id)
                .outerjoin(DistrictModel, DistrictModel.code == AddressModel.district_code)
                .offset(rng.randrange(int(total)))
                .limit(1)
            )
        ).first()
        if row is None:
            return FALLBACK_ADDRESS
        a, street, district_name, okrug = row
        return AddressFacts(
            street=street,
            house=a.house,
            building=a.building,
            structure=a.structure,
            district=a.district_code,
            district_name=district_name,
            okrug=okrug,
            lat=a.lat,
            lon=a.lon,
        )

    async def resolve_services(
        self, incident_code: str, flags: list[str], okrug: str | None, district: str | None
    ) -> list[ServiceFacts]:
        resolved = await ResolveServicesHandler(self._reader)(
            ResolveServices(incident_types=[incident_code], flags=flags, okrug=okrug, district=district)
        )
        return [ServiceFacts(code=s.code, short=s.short, main=s.main, phone=s.phone) for s in resolved.services]


class IncidentCardContext:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def dds_context(self, card_id: UUID, service_code: str) -> DdsCallContext | None:
        card = await SqlCardReader(self._s).get(card_id)
        if card is None or card.status == "draft":
            return None
        own = next((s for s in card.services if s.code == service_code), None)
        if own is None:
            return None
        scenario_id = (
            await self._s.execute(select(IncidentCardModel.scenario_id).where(IncidentCardModel.id == card_id))
        ).scalar_one_or_none()
        order_no = next((h.order_no for h in reversed(own.history) if h.order_no), None)
        data = card.data
        victims = data.get("victims") or {}
        title = {s.value: t for s, t in TITLES.items()}
        return DdsCallContext(
            card_id=card.id,
            card_number=card.number,
            scenario_id=scenario_id,
            address=card.address_line,
            victims=str(victims.get("count") or "нет") if victims.get("has") else "нет",
            applicant_phone=(data.get("phones") or {}).get("provided") or (data.get("phones") or {}).get("aon") or "",
            applicant_name=(data.get("applicant") or {}).get("name") or "",
            description=data.get("description") or "",
            service_status=own.status if own.status in ServiceStatus._value2member_map_ else "received",
            order_no=order_no,
            services={s.code: (s.short, title.get(s.status, s.status)) for s in card.services},
        )

    async def card_aon(self, card_id: UUID) -> str | None:
        card = await SqlCardReader(self._s).get(card_id)
        return (card.data.get("phones") or {}).get("aon") if card else None
