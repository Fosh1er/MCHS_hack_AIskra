"""Адаптеры адресного справочника (п. 1.2): файлы data/dictionaries → БД, SQL-чтение для подсказок и карты."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import and_, delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.dictionaries.application.ports.addresses import (
    AddressPayload,
    AddressRow,
    DistrictShape,
    HouseRecord,
    StreetRow,
)
from aiskra.modules.dictionaries.domain.address import house_key, same_house_number
from aiskra.modules.dictionaries.infrastructure.models import (
    AddressModel,
    DistrictModel,
    DistrictShapeModel,
    StreetModel,
)
from aiskra.shared.errors import DomainError
from aiskra.shared.text import search_key

ADDRESSES_FILE = "addresses.csv.gz"
SHAPES_FILE = "districts_geo.json"


class FileAddressSource:
    """addresses.csv.gz + districts_geo.json из генератора data/tools/build_addresses.py."""

    def __init__(self, directory: Path) -> None:
        self._dir = directory

    def read(self) -> AddressPayload:
        csv_path, geo_path = self._dir / ADDRESSES_FILE, self._dir / SHAPES_FILE
        for path in (csv_path, geo_path):
            if not path.exists():
                raise DomainError(f"Нет файла адресного справочника: {path}", code="source_missing")
        raw = csv_path.read_bytes()
        reader = csv.DictReader(io.StringIO(gzip.decompress(raw).decode("utf-8")), delimiter=";")
        houses = [
            HouseRecord(
                street=r["street"],
                house=r["house"],
                building=r["building"],
                structure=r["structure"],
                lat=float(r["lat"]),
                lon=float(r["lon"]),
                district=r["district"],
            )
            for r in reader
        ]
        geo: dict[str, Any] = json.loads(geo_path.read_text(encoding="utf-8"))
        shapes = [
            DistrictShape(
                district=f["properties"]["code"],
                name=f["properties"]["name"],
                okrug=f["properties"]["okrug"],
                geometry=f["geometry"],
                label_lon=float(f["properties"]["label"][0]),
                label_lat=float(f["properties"]["label"][1]),
            )
            for f in geo["features"]
        ]
        digest = hashlib.sha256(raw + geo_path.read_bytes()).hexdigest()
        return AddressPayload(source_file=ADDRESSES_FILE, source_sha256=digest, houses=houses, shapes=shapes)


class SqlAddressWriter:
    def __init__(self, session: AsyncSession, chunk: int = 2000) -> None:
        self._s = session
        self._chunk = chunk

    async def replace(self, payload: AddressPayload) -> dict[str, int]:
        s = self._s
        okrug_of = dict((await s.execute(select(DistrictModel.code, DistrictModel.okrug_code))).all())
        await s.execute(delete(AddressModel))
        await s.execute(delete(StreetModel))
        await s.execute(delete(DistrictShapeModel))

        by_street: dict[str, list[HouseRecord]] = defaultdict(list)
        for h in payload.houses:
            by_street[h.street].append(h)
        streets, street_id = [], {}
        for i, (name, houses) in enumerate(sorted(by_street.items()), start=1):
            districts = sorted({h.district for h in houses if h.district})
            okrugs = {okrug_of.get(d) for d in districts} - {None}
            mid = houses[len(houses) // 2]
            street_id[name] = i
            streets.append(
                {
                    "id": i,
                    "name": name,
                    "search_key": search_key(name),
                    "districts": districts,
                    "okrug_code": okrugs.pop() if len(okrugs) == 1 else None,
                    "lat": mid.lat,
                    "lon": mid.lon,
                }
            )
        rows = [
            {
                "id": i,
                "street_id": street_id[h.street],
                "house": h.house,
                "building": h.building,
                "structure": h.structure,
                "house_key": house_key(h.house, h.building, h.structure),
                "district_code": h.district,
                "lat": h.lat,
                "lon": h.lon,
            }
            for i, h in enumerate(payload.houses, start=1)
        ]
        for table, data in ((StreetModel, streets), (AddressModel, rows)):
            for start in range(0, len(data), self._chunk):
                await s.execute(insert(table), data[start : start + self._chunk])
        await s.execute(
            insert(DistrictShapeModel),
            [
                {
                    "district_code": sh.district,
                    "name": sh.name,
                    "okrug_code": sh.okrug,
                    "geometry": sh.geometry,
                    "label_lat": sh.label_lat,
                    "label_lon": sh.label_lon,
                }
                for sh in payload.shapes
            ],
        )
        return {"houses": len(rows), "streets": len(streets), "shapes": len(payload.shapes)}


class SqlAddressReader:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    def _street_filter(self, terms: list[str]) -> Any:
        return and_(*[StreetModel.search_key.contains(search_key(t), autoescape=True) for t in terms])

    async def _okrugs(self) -> dict[str, str]:
        return dict((await self._s.execute(select(DistrictModel.code, DistrictModel.okrug_code))).all())

    async def houses(
        self, street_terms: list[str], house_prefix: str, *, exact_house: bool, limit: int
    ) -> list[AddressRow]:
        cond = (
            AddressModel.house_key == house_prefix
            if exact_house
            else AddressModel.house_key.startswith(house_prefix, autoescape=True)
        )
        stmt = (
            select(StreetModel.name, AddressModel)
            .join(StreetModel, StreetModel.id == AddressModel.street_id)
            .where(self._street_filter(street_terms), cond)
            .limit(limit * 20)
        )
        # «13» — это 13, 13А, 13/2, 13 к1, но не 130: префикс в SQL, границу номера проверяем здесь
        found = [r for r in (await self._s.execute(stmt)).all() if same_house_number(r[1].house_key, house_prefix)]
        okrugs = await self._okrugs()
        # точное совпадение номера — первым, затем короткие названия улиц, затем порядок номеров
        found = sorted(
            found, key=lambda r: (r[1].house_key != house_prefix, len(r[0]), r[0], len(r[1].house_key), r[1].house_key)
        )
        return [
            AddressRow(
                street=name,
                house=a.house,
                building=a.building,
                structure=a.structure,
                lat=a.lat,
                lon=a.lon,
                district=a.district_code,
                okrug=okrugs.get(a.district_code, ""),
            )
            for name, a in found[:limit]
        ]

    async def streets(self, street_terms: list[str], limit: int) -> list[StreetRow]:
        stmt = select(StreetModel).where(self._street_filter(street_terms)).limit(limit * 5)
        rows = sorted((await self._s.execute(stmt)).scalars().all(), key=lambda s: (len(s.name), s.name))
        return [
            StreetRow(name=s.name, okrug=s.okrug_code or "", districts=list(s.districts), lat=s.lat, lon=s.lon)
            for s in rows[:limit]
        ]

    async def in_box(
        self, min_lat: float, min_lon: float, max_lat: float, max_lon: float, limit: int
    ) -> list[AddressRow]:
        stmt = (
            select(StreetModel.name, AddressModel)
            .join(StreetModel, StreetModel.id == AddressModel.street_id)
            .where(AddressModel.lat.between(min_lat, max_lat), AddressModel.lon.between(min_lon, max_lon))
            .limit(limit)
        )
        okrugs = await self._okrugs()
        return [
            AddressRow(
                street=name,
                house=a.house,
                building=a.building,
                structure=a.structure,
                lat=a.lat,
                lon=a.lon,
                district=a.district_code,
                okrug=okrugs.get(a.district_code, ""),
            )
            for name, a in (await self._s.execute(stmt)).all()
        ]

    async def shapes(self) -> list[DistrictShape]:
        rows = (await self._s.execute(select(DistrictShapeModel))).scalars().all()
        return [
            DistrictShape(
                district=r.district_code,
                name=r.name,
                okrug=r.okrug_code,
                geometry=r.geometry,
                label_lon=r.label_lon,
                label_lat=r.label_lat,
            )
            for r in rows
        ]
