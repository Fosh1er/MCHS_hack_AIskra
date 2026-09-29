"""Порты модуля training: факты из справочников, хранилище сценариев и звонков, контекст карточки."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from aiskra.modules.training.domain.call import Call, CallMessage
from aiskra.modules.training.domain.scenario import AddressFacts, IncidentFacts, Scenario, ServiceFacts


class ScenarioFactsSource(Protocol):
    """Справочники (модуль dictionaries) для генерации — адаптер в composition root (ADR-0001)."""

    async def pick_incident(self, rng: random.Random, groups: list[int] | None) -> IncidentFacts: ...

    async def pick_address(self, rng: random.Random) -> AddressFacts: ...

    async def resolve_services(
        self, incident_code: str, flags: list[str], okrug: str | None, district: str | None
    ) -> list[ServiceFacts]: ...


@dataclass(frozen=True)
class ScenarioRow:
    id: UUID
    title: str
    status: str
    difficulty: int
    card_type_code: str | None
    incident_type_code: str | None
    source: str
    created_at: Any
    psy_profile: str | None = None  # п. 3.6


class ScenarioRepository(Protocol):
    async def add(self, scenario: Scenario) -> None: ...

    async def get(self, scenario_id: UUID) -> Scenario | None: ...

    async def save(self, scenario: Scenario) -> None: ...

    async def page(
        self,
        *,
        status: str | None,
        difficulty: int | None,
        card_type: str | None,
        source: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ScenarioRow], int]: ...

    async def random_approved(
        self, rng: random.Random, groups: list[int] | None, difficulty: int | None = None
    ) -> Scenario | None:
        """Случайный утверждённый сценарий групп; `difficulty` — ближайшие к ней по сложности."""
        ...


class CallRepository(Protocol):
    async def add(self, call: Call) -> None: ...

    async def get(self, call_id: UUID) -> Call | None: ...

    async def save(self, call: Call) -> None: ...

    async def add_message(self, message: CallMessage) -> None: ...

    async def messages(self, call_id: UUID) -> list[CallMessage]: ...

    async def calls_of_card(self, card_id: UUID, student_id: UUID | None) -> list[Call]: ...


@dataclass(frozen=True)
class DdsCallContext:
    """Карточка глазами ДДС для звонков (модуль incidents — адаптер в composition root)."""

    card_id: UUID
    card_number: int
    scenario_id: UUID | None
    address: str | None
    victims: str
    applicant_phone: str
    applicant_name: str
    description: str
    service_status: str
    order_no: str | None
    services: dict[str, tuple[str, str]]  # код → (короткое имя, текущий статус)


class CardContextSource(Protocol):
    async def dds_context(self, card_id: UUID, service_code: str) -> DdsCallContext | None: ...

    async def card_aon(self, card_id: UUID) -> str | None: ...
