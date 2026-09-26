"""Запросы по справочникам: службы, округа и районы, перечисления (статусы, каналы связи, признаки)."""

from __future__ import annotations

from dataclasses import dataclass

from aiskra.modules.dictionaries.application.ports.reader import (
    DictionaryReader,
    DistrictRow,
    EnumValueRow,
    OkrugRow,
    ServiceRow,
)
from aiskra.modules.dictionaries.domain.model import search_form
from aiskra.shared.application import Query
from aiskra.shared.errors import NotFoundError


@dataclass(frozen=True, kw_only=True)
class ListServices(Query):
    """Справочник служб (модал «Добавьте службы»): поиск по короткому и полному названию."""

    q: str = ""
    kinds: list[str] | None = None
    okrug: str | None = None
    limit: int = 500


class ListServicesHandler:
    def __init__(self, reader: DictionaryReader) -> None:
        self._reader = reader

    async def __call__(self, query: ListServices) -> list[ServiceRow]:
        return await self._reader.list_services(
            kinds=query.kinds, okrug=query.okrug, terms=search_form(query.q).split(), limit=min(query.limit, 1000)
        )


@dataclass(frozen=True, kw_only=True)
class ListTerritory(Query):
    okrug: str | None = None
    q: str = ""


@dataclass(frozen=True)
class Territory:
    okrugs: list[OkrugRow]
    districts: list[DistrictRow]


class ListTerritoryHandler:
    def __init__(self, reader: DictionaryReader) -> None:
        self._reader = reader

    async def __call__(self, query: ListTerritory) -> Territory:
        return Territory(
            okrugs=await self._reader.list_okrugs(),
            districts=await self._reader.list_districts(okrug=query.okrug, terms=search_form(query.q).split()),
        )


@dataclass(frozen=True, kw_only=True)
class ListEnum(Query):
    """Значения перечисления: applicant_status, card_status, service_status, telephony_status, card_flag, channel."""

    domain: str


class ListEnumHandler:
    def __init__(self, reader: DictionaryReader) -> None:
        self._reader = reader

    async def __call__(self, query: ListEnum) -> list[EnumValueRow]:
        rows = await self._reader.list_enum(query.domain)
        if not rows:
            domains = await self._reader.list_enum_domains()
            raise NotFoundError(f"Справочник «{query.domain}» не найден. Доступны: {', '.join(domains)}")
        return rows
