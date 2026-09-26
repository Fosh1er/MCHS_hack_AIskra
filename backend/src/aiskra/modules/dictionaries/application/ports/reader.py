"""Порт чтения справочников (CQRS-lite: запросы читают напрямую, минуя домен)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class IncidentTypeRow:
    code: str
    group_id: int
    group_title: str
    sign1: str | None
    sign2: str | None
    sign3: str | None
    final_type: str | None
    ekp_type: str | None
    response_scenario: str | None
    main_services: list[str]
    visible_to_112: bool
    operator_hint: str | None


@dataclass(frozen=True)
class RoutingCell:
    col: int
    service: str
    service_short: str | None
    recipient: str | None
    flag: str | None
    base: str | None
    audience: str
    delivery: str
    service_type: str | None


@dataclass(frozen=True)
class CardTypeRow:
    code: str
    title: str
    kind: str
    group_id: int | None
    sign1: list[str]
    synonyms: list[str]
    quick: bool
    significant: bool


@dataclass(frozen=True)
class ServiceRow:
    code: str
    short: str
    full: str
    kind: str
    okrug: str | None
    district: str | None
    phone: str
    phone_synthetic: bool
    confirmed: bool
    source: str
    main_codes: list[str] = field(default_factory=list)  # коды «Главной службы» классификатора (колонка 14)
    integrated: bool = True  # False — служба без интеграции с системой 112 (серая плашка)


@dataclass(frozen=True)
class OkrugRow:
    code: str
    short: str
    name: str
    prefecture: str | None


@dataclass(frozen=True)
class DistrictRow:
    code: str
    name: str
    okrug: str
    kind: str
    dds: str
    aliases: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EnumValueRow:
    domain: str
    code: str
    name: str
    sort: int
    attrs: dict[str, object]


class DictionaryReader(Protocol):
    async def search_incident_types(
        self,
        *,
        terms: list[str],
        groups: list[int] | None,
        sign1: list[str] | None,
        visible_only: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[IncidentTypeRow], int]: ...

    async def get_incident_type(self, code: str) -> IncidentTypeRow | None: ...

    async def get_routing(self, code: str) -> list[RoutingCell]: ...

    async def list_card_types(self) -> list[CardTypeRow]: ...

    async def get_card_type(self, code: str) -> CardTypeRow | None: ...

    async def list_services(
        self, *, kinds: list[str] | None, okrug: str | None, terms: list[str], limit: int
    ) -> list[ServiceRow]: ...

    async def get_services(self, codes: list[str]) -> list[ServiceRow]: ...

    async def list_main_services(self) -> list[ServiceRow]:
        """Службы, у которых есть коды «Главной службы» классификатора."""
        ...

    async def get_district(self, code: str) -> DistrictRow | None: ...

    async def list_okrugs(self) -> list[OkrugRow]: ...

    async def list_districts(self, *, okrug: str | None, terms: list[str]) -> list[DistrictRow]: ...

    async def list_enum(self, domain: str) -> list[EnumValueRow]: ...

    async def list_enum_domains(self) -> list[str]: ...
