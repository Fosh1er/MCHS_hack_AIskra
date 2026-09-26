"""Порты адресного справочника (п. 1.2): источник файлов, запись и чтение."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class HouseRecord:
    """Дом из addresses.csv.gz: улица, номер, корпус, строение, координаты, район АРМ."""

    street: str
    house: str
    building: str
    structure: str
    lat: float
    lon: float
    district: str


@dataclass(frozen=True)
class DistrictShape:
    """Упрощённая граница района АРМ (GeoJSON-геометрия) и точка подписи на карте."""

    district: str
    name: str
    okrug: str
    geometry: dict[str, Any]
    label_lon: float
    label_lat: float


@dataclass
class AddressPayload:
    source_file: str
    source_sha256: str
    houses: list[HouseRecord]
    shapes: list[DistrictShape]


class AddressSource(Protocol):
    def read(self) -> AddressPayload: ...


class AddressWriter(Protocol):
    async def replace(self, payload: AddressPayload) -> dict[str, int]:
        """Заменить справочник целиком (на адреса ничего не ссылается: карточка хранит адрес текстом)."""
        ...


@dataclass(frozen=True)
class AddressRow:
    """Дом для подсказки, карты и обратного геокодирования."""

    street: str
    house: str
    building: str
    structure: str
    lat: float
    lon: float
    district: str
    okrug: str


@dataclass(frozen=True)
class StreetRow:
    name: str
    okrug: str
    districts: list[str] = field(default_factory=list)
    lat: float | None = None
    lon: float | None = None


class AddressReader(Protocol):
    async def houses(
        self, street_terms: list[str], house_prefix: str, *, exact_house: bool, limit: int
    ) -> list[AddressRow]:
        """Дома на улицах, в названии которых есть все слова; номер — точный или по началу."""
        ...

    async def streets(self, street_terms: list[str], limit: int) -> list[StreetRow]: ...

    async def in_box(
        self, min_lat: float, min_lon: float, max_lat: float, max_lon: float, limit: int
    ) -> list[AddressRow]: ...

    async def shapes(self) -> list[DistrictShape]: ...
