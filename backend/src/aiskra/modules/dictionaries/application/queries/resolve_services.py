"""Запрос: автоматический список служб карточки 112 по типам происшествия, признакам и адресу.

Основа пункта 1.5 («Автоподбор служб»), нужна панели служб карточки (п. 1.1):
1. Для каждого конечного типа классификатора применяются колонки матрицы (`domain/routing.py`).
2. Территориальные мета-службы разворачиваются по адресу: «Территориальные ОИВ» → ДДС префектуры округа
   и ДДС района; «… ТиНАО» — то же для ТиНАО; «Автомобильные дороги АО» → ГБУ АД округа.
   Если адрес ещё не указан, возвращается признак `needs_address`.
   Службы по подчинённости объекта (поле «Объект», пп. 4.4, 8.4) — по справочнику `subordination.yaml`.
3. «Главная служба» типа (колонка 14 классификатора) отмечается как основная и добавляется, даже если
   матрица её не дала. На панели основная служба подчёркнута двойной линией.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from aiskra.modules.dictionaries.application.ports.reader import DictionaryReader, ServiceRow
from aiskra.modules.dictionaries.domain.model import DeliveryKind
from aiskra.modules.dictionaries.domain.routing import Cell, applicable, territorial_applies
from aiskra.modules.dictionaries.domain.subordination import SubordinationRule, subordinate_services
from aiskra.shared.application import Query
from aiskra.shared.errors import NotFoundError

TERRITORIAL = frozenset({"territorial", "territorial_tinao", "territorial_roads"})
MAX_TYPES = 10


@dataclass(frozen=True, kw_only=True)
class ResolveServices(Query):
    incident_types: list[str]
    flags: list[str] = field(default_factory=list)
    okrug: str | None = None
    district: str | None = None
    object_name: str | None = None  # поле «Объект» адреса карточки — для подчинённости объекта


@dataclass(frozen=True, kw_only=True)
class ResolvedService:
    code: str
    short: str
    full: str
    kind: str
    phone: str
    main: bool
    integrated: bool  # False — серая плашка «без интеграции», как «Деп. ЖКХ» на стенде
    service_type: str | None  # «Класс.:» для службы, если в ячейке указан её тип
    reasons: list[str]  # почему служба в списке: тип и колонка классификатора, главная служба, территория


@dataclass(frozen=True, kw_only=True)
class ResolvedServices:
    services: list[ResolvedService]
    monitoring: list[str]  # информационные подписчики (не на панели)
    needs_address: bool  # есть территориальные службы, но округ/район не указаны


class ResolveServicesHandler:
    def __init__(self, reader: DictionaryReader, subordination: Sequence[SubordinationRule] = ()) -> None:
        self._reader = reader
        self._subordination = subordination

    async def __call__(self, query: ResolveServices) -> ResolvedServices:
        codes = list(dict.fromkeys(query.incident_types))[:MAX_TYPES]
        flags = set(query.flags)
        okrug = query.okrug
        district = await self._reader.get_district(query.district) if query.district else None
        if district is not None:
            okrug = district.okrug

        reasons: dict[str, list[str]] = {}
        service_types: dict[str, str] = {}
        main_codes: set[str] = set()
        monitoring: set[str] = set()
        needs_address = False

        def add(service: str, reason: str) -> None:
            reasons.setdefault(service, [])
            if reason not in reasons[service]:
                reasons[service].append(reason)

        for code in codes:
            row = await self._reader.get_incident_type(code)
            if row is None:
                raise NotFoundError(f"Тип происшествия {code} не найден", code="incident_type_not_found")
            main_codes.update(row.main_services)
            cells = [
                Cell(
                    col=c.col,
                    service=c.service,
                    flag=c.flag,
                    base=c.base,
                    audience=c.audience,
                    delivery=DeliveryKind(c.delivery),
                    service_type=c.service_type,
                )
                for c in await self._reader.get_routing(code)
            ]
            for hit in applicable(cells, flags):
                if hit.monitoring:
                    monitoring.add(hit.service)
                    continue
                reason = f"{code}: колонка {hit.col}" + (f" (признак {hit.flag})" if hit.flag else "")
                if hit.service in TERRITORIAL:
                    if not territorial_applies(hit.service, okrug):
                        continue
                    targets = await self._territorial(hit.service, okrug, district.dds if district else None)
                    needs_address = needs_address or not targets
                    for target in targets:
                        add(target, f"{reason}, территория")
                    continue
                add(hit.service, reason)
                if hit.service_type:
                    service_types.setdefault(hit.service, hit.service_type)

        for rule in subordinate_services(self._subordination, query.object_name):
            add(rule.service, f"подчинённость объекта: {rule.note}")

        main_services = [s for s in await self._reader.list_main_services() if set(s.main_codes) & main_codes]
        for s in main_services:
            add(s.code, "главная служба типа")
        main_set = {s.code for s in main_services}

        rows = {s.code: s for s in await self._reader.get_services(list(reasons))}
        ordered = sorted(rows.values(), key=lambda s: (s.code not in main_set, _kind_order(s), s.short))
        return ResolvedServices(
            services=[
                ResolvedService(
                    code=s.code,
                    short=s.short,
                    full=s.full,
                    kind=s.kind,
                    phone=s.phone,
                    main=s.code in main_set,
                    integrated=s.integrated,
                    service_type=service_types.get(s.code),
                    reasons=reasons[s.code],
                )
                for s in ordered
            ],
            monitoring=sorted(monitoring),
            needs_address=needs_address,
        )

    async def _territorial(self, service: str, okrug: str | None, district_dds: str | None) -> list[str]:
        if okrug is None:
            return []
        if service == "territorial_roads":
            roads = await self._reader.list_services(kinds=["okrug_roads"], okrug=okrug, terms=[], limit=5)
            return [r.code for r in roads]
        # префектура — из справочника округов: ТиНАО (НАО и ТАО) обслуживает одна префектура
        prefecture = next((o.prefecture for o in await self._reader.list_okrugs() if o.code == okrug), None)
        return [code for code in (prefecture, district_dds) if code]


_KIND_ORDER = {"emergency": 0, "federal": 1, "city": 2, "utility": 3, "transport": 4, "department": 5}


def _kind_order(s: ServiceRow) -> int:
    return _KIND_ORDER.get(s.kind, 9)
