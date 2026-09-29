"""Запись справочников: upsert по естественным ключам + мягкая деактивация пропавших записей.

Типы происшествий, службы и районы могут быть связаны с данными других модулей (сценарии, карточки),
поэтому они не удаляются, а помечаются active=false. Матрица служб, типы карточки и перечисления
перезаписываются целиком.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.dictionaries.application.ports.sources import DictionaryPayload, WriteStats
from aiskra.modules.dictionaries.domain.model import search_form
from aiskra.modules.dictionaries.infrastructure.models import (
    BrigadeModel,
    CardTypeModel,
    DistrictModel,
    EnumValueModel,
    ImportRunModel,
    IncidentGroupModel,
    IncidentTypeModel,
    OkrugModel,
    RoutingModel,
    ServiceColumnModel,
    ServiceModel,
)
from aiskra.platform.db import upsert


class SqlDictionaryWriter:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def _deactivate(self, model: Any, key: Any, keep: set[str]) -> int:
        result = await self._s.execute(
            update(model).where(key.not_in(keep), model.active.is_(True)).values(active=False)
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def replace(self, p: DictionaryPayload) -> WriteStats:
        s = self._s
        stats = WriteStats()
        await upsert(s, IncidentGroupModel, [{"id": k, "title": v} for k, v in sorted(p.groups.items())], ["id"])

        types = [
            {
                "code": t.code.value,
                "group_id": t.group_id,
                "sign1": t.sign1,
                "sign1_key": search_form(t.sign1) if t.sign1 else None,
                "sign2": t.sign2,
                "sign3": t.sign3,
                "operator_hint": t.operator_hint,
                "final_type": t.final_type,
                "ekp_type": t.ekp_type,
                "response_scenario": t.response_scenario,
                "main_services": t.main_services,
                "visible_to_112": t.visible_to_112,
                "search_text": t.search_text(),
                "active": True,
            }
            for t in p.incident_types
        ]
        await upsert(s, IncidentTypeModel, types, ["code"])
        stats.deactivated["incident_types"] = await self._deactivate(
            IncidentTypeModel, IncidentTypeModel.code, {t.code.value for t in p.incident_types}
        )

        await s.execute(delete(RoutingModel))
        await s.execute(delete(ServiceColumnModel))
        await s.execute(
            insert(ServiceColumnModel),
            [
                {
                    "col": c.col,
                    "service_code": c.service,
                    "header": c.header,
                    "recipient": c.recipient,
                    "flag": c.flag,
                    "base": c.base,
                    "audience": c.audience,
                }
                for c in p.columns
            ],
        )
        routing = [
            {"incident_type_code": t.code.value, "col": col, "delivery": d.kind.value, "service_type": d.service_type}
            for t in p.incident_types
            for col, d in t.routing.items()
        ]
        await s.execute(insert(RoutingModel), routing)

        services = [
            {
                "code": x["code"],
                "short_name": x["short"],
                "full_name": x["full"],
                "kind": x["kind"],
                "okrug_code": x.get("okrug"),
                "district_code": x.get("district"),
                "main_codes": x.get("main_codes", []),
                "phone": x["phone"],
                "phone_synthetic": x["phone_synthetic"],
                "confirmed": x["confirmed"],
                "integrated": x.get("integrated", True),
                "source": x["source"],
                "search_text": search_form(f"{x['short']} {x['full']}"),
                "active": True,
            }
            for x in p.services
        ]
        await upsert(s, ServiceModel, services, ["code"])
        stats.deactivated["services"] = await self._deactivate(
            ServiceModel, ServiceModel.code, {x["code"] for x in services}
        )

        if p.brigades:  # п. 5.5: после служб — бригада ссылается на службу
            await upsert(s, BrigadeModel, p.brigades, ["code"])
        stats.deactivated["brigades"] = await self._deactivate(
            BrigadeModel, BrigadeModel.code, {b["code"] for b in p.brigades}
        )

        await upsert(
            s,
            OkrugModel,
            [
                {
                    "code": o["code"],
                    "short": o["short"],
                    "name": o["name"],
                    "prefecture_code": o.get("prefecture"),
                    "outside_moscow": bool(o.get("outside_moscow", False)),
                }
                for o in p.okrugs
            ],
            ["code"],
        )
        districts = [
            {
                "code": d["code"],
                "name": d["name"],
                "okrug_code": d["okrug"],
                "kind": d["kind"],
                "dds_service_code": d["dds"],
                "aliases": d.get("aliases", []),
                "search_text": search_form(" ".join([d["name"], *d.get("aliases", [])])),
                "active": True,
            }
            for d in p.districts
        ]
        await upsert(s, DistrictModel, districts, ["code"])
        stats.deactivated["districts"] = await self._deactivate(
            DistrictModel, DistrictModel.code, {d["code"] for d in districts}
        )

        await s.execute(delete(CardTypeModel))
        await s.execute(
            insert(CardTypeModel),
            [
                {
                    "code": c["code"],
                    "title": c["title"],
                    "kind": c["kind"],
                    "group_id": c.get("group"),
                    "sign1": c.get("sign1", []),
                    "synonyms": c.get("synonyms", []),
                    "quick": bool(c.get("quick")),
                    "significant": bool(c.get("significant")),
                    "sort": i,
                }
                for i, c in enumerate(p.card_types)
            ],
        )

        await s.execute(delete(EnumValueModel))
        enum_rows = [
            {"domain": domain, "code": v["code"], "name": v["name"], "sort": i, "attrs": v.get("attrs", {})}
            for domain, values in p.enums.items()
            for i, v in enumerate(values)
        ]
        enum_rows += [
            {
                "domain": "channel",
                "code": c["code"],
                "name": c["name"],
                "sort": i,
                "attrs": {"confirmed": c.get("confirmed", True), "auto_detect": c.get("auto_detect", False)},
            }
            for i, c in enumerate(p.channels)
        ]
        await s.execute(insert(EnumValueModel), enum_rows)

        stats.counts = {
            "groups": len(p.groups),
            "incident_types": len(types),
            "incident_types_visible_to_112": sum(1 for t in types if t["visible_to_112"]),
            "service_columns": len(p.columns),
            "routing_cells": len(routing),
            "services": len(services),
            "brigades": len(p.brigades),
            "okrugs": len(p.okrugs),
            "districts": len(districts),
            "card_types": len(p.card_types),
            "enum_values": len(enum_rows),
        }
        s.add(
            ImportRunModel(source_file=p.source_file, source_sha256=p.source_sha256, counts=stats.counts, warnings=[])
        )
        return stats


async def count_rows(session: AsyncSession, model: Any) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())
