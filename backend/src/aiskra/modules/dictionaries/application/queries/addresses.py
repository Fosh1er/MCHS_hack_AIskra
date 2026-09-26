"""Запросы адресного справочника (п. 1.2): подсказки единой адресной строки, адрес по точке на карте,
дома в окне карты, границы районов.

Источник данных — OpenStreetMap (data/tools/build_addresses.py): в тренажёре он заменяет подсказки
Яндекс.Карт / ФИАС реального АРМ (instr/image20), без доступа к внешним сетям."""

from __future__ import annotations

from dataclasses import dataclass, field

from aiskra.modules.dictionaries.application.ports.addresses import AddressReader, AddressRow, DistrictShape
from aiskra.modules.dictionaries.domain.address import (
    address_label,
    distance_m,
    geometry_bbox,
    house_key,
    parse_query,
    point_in_geometry,
)
from aiskra.shared.application import Query
from aiskra.shared.errors import DomainError

SOURCE = "справочник"  # правая колонка списка подсказок (в оригинале — «Яндекс», «ФИАС»)
NEAR_RADIUS_M = 120  # дальше этого дом по точке не подставляется — только район
MAX_BOX_DEG = 0.05  # окно карты для точек домов: ≈ 5 × 3 км, чтобы не отдавать весь город


@dataclass(frozen=True)
class AddressSuggestion:
    """Вариант подсказки: подпись, разобранные поля, район и координаты (выбор заполняет блок «Адрес»)."""

    label: str
    street: str
    house: str
    building: str
    structure: str
    district: str | None
    okrug: str | None
    lat: float | None
    lon: float | None
    source: str = SOURCE


def _suggestion(row: AddressRow) -> AddressSuggestion:
    return AddressSuggestion(
        label=address_label(row.street, row.house, row.building, row.structure),
        street=row.street,
        house=row.house,
        building=row.building,
        structure=row.structure,
        district=row.district or None,
        okrug=row.okrug or None,
        lat=row.lat,
        lon=row.lon,
    )


@dataclass(frozen=True, kw_only=True)
class SuggestAddresses(Query):
    q: str
    limit: int = 10


class SuggestAddressesHandler:
    """Без номера дома — улицы (район и координаты — по середине улицы); с номером — дома этой улицы.

    Если такого дома в справочнике нет, возвращается улица без номера: оператор допишет дом вручную
    (в OSM есть не все дома)."""

    def __init__(self, reader: AddressReader) -> None:
        self._reader = reader

    async def __call__(self, query: SuggestAddresses) -> list[AddressSuggestion]:
        parsed = parse_query(query.q)
        terms = [t for t in parsed.street_terms if len(t) >= 2 or t.isdigit()]
        if not any(any(ch.isalpha() for ch in t) for t in terms):
            return []  # одни цифры — это номер дома без улицы
        limit = max(1, min(query.limit, 30))
        if parsed.house:
            key = house_key(parsed.house, parsed.building, parsed.structure)
            exact = bool(parsed.building or parsed.structure)
            rows = await self._reader.houses(terms, key, exact_house=exact, limit=limit)
            if rows:
                return [_suggestion(r) for r in rows]
        streets = await self._reader.streets(terms, limit)
        return [
            AddressSuggestion(
                label=s.name,
                street=s.name,
                house="",
                building="",
                structure="",
                district=s.districts[0] if len(s.districts) == 1 else None,
                okrug=s.okrug or None,
                lat=s.lat,
                lon=s.lon,
            )
            for s in streets
        ]


@dataclass(frozen=True, kw_only=True)
class ReverseGeocode(Query):
    """Адрес по точке: «Указать на карте» или ввод координат + «ОК» (instr/image27, image28)."""

    lat: float
    lon: float


@dataclass(frozen=True)
class GeocodeResult:
    lat: float
    lon: float
    district: str | None
    okrug: str | None
    address: AddressSuggestion | None
    distance_m: float | None


class ReverseGeocodeHandler:
    def __init__(self, reader: AddressReader) -> None:
        self._reader = reader

    async def __call__(self, query: ReverseGeocode) -> GeocodeResult:
        if not (-90 <= query.lat <= 90 and -180 <= query.lon <= 180):
            raise DomainError("Координаты вне допустимого диапазона", code="bad_coordinates")
        district = okrug = None
        for shape in await self._reader.shapes():
            min_lon, min_lat, max_lon, max_lat = geometry_bbox(shape.geometry)
            inside_box = min_lon <= query.lon <= max_lon and min_lat <= query.lat <= max_lat
            if inside_box and point_in_geometry(query.lon, query.lat, shape.geometry):
                district, okrug = shape.district, shape.okrug
                break
        d_lat = NEAR_RADIUS_M / 111_000
        d_lon = d_lat * 1.8  # Москва ~55,7° с.ш.: градус долготы ≈ 63 км
        rows = await self._reader.in_box(
            query.lat - d_lat, query.lon - d_lon, query.lat + d_lat, query.lon + d_lon, limit=500
        )
        best = min(rows, key=lambda r: distance_m(query.lat, query.lon, r.lat, r.lon), default=None)
        dist = distance_m(query.lat, query.lon, best.lat, best.lon) if best else None
        near = best if best and dist is not None and dist <= NEAR_RADIUS_M else None
        return GeocodeResult(
            lat=query.lat,
            lon=query.lon,
            district=district or (near.district if near else None),
            okrug=okrug or (near.okrug if near else None),
            address=_suggestion(near) if near else None,
            distance_m=round(dist, 1) if near and dist is not None else None,
        )


@dataclass(frozen=True, kw_only=True)
class HousesInBox(Query):
    """Точки домов в окне карты (слой «Дома» при крупном масштабе)."""

    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float
    limit: int = 1500


@dataclass(frozen=True)
class HousePoint:
    label: str
    lat: float
    lon: float


class HousesInBoxHandler:
    def __init__(self, reader: AddressReader) -> None:
        self._reader = reader

    async def __call__(self, query: HousesInBox) -> list[HousePoint]:
        if query.max_lat - query.min_lat > MAX_BOX_DEG or query.max_lon - query.min_lon > MAX_BOX_DEG * 1.8:
            return []  # мелкий масштаб: дома не показываются
        rows = await self._reader.in_box(
            query.min_lat, query.min_lon, query.max_lat, query.max_lon, limit=min(query.limit, 3000)
        )
        return [
            HousePoint(label=address_label(r.street, r.house, r.building, r.structure), lat=r.lat, lon=r.lon)
            for r in rows
        ]


@dataclass(frozen=True, kw_only=True)
class DistrictShapes(Query):
    pass


@dataclass(frozen=True)
class GeoFeature:
    properties: dict[str, object]
    geometry: dict[str, object]
    type: str = "Feature"


@dataclass(frozen=True)
class GeoCollection:
    features: list[GeoFeature] = field(default_factory=list)
    attribution: str = "© участники OpenStreetMap (ODbL)"
    type: str = "FeatureCollection"


class DistrictShapesHandler:
    def __init__(self, reader: AddressReader) -> None:
        self._reader = reader

    async def __call__(self, query: DistrictShapes) -> GeoCollection:
        shapes: list[DistrictShape] = await self._reader.shapes()
        return GeoCollection(
            features=[
                GeoFeature(
                    properties={
                        "code": s.district,
                        "name": s.name,
                        "okrug": s.okrug,
                        "label": [s.label_lon, s.label_lat],
                    },
                    geometry=s.geometry,
                )
                for s in shapes
            ]
        )
