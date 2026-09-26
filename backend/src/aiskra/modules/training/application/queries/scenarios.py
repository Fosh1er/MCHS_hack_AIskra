"""Запросы банка сценариев (п. 3.2): список и сценарий целиком — для проверки и утверждения преподавателем (4.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from aiskra.modules.training.application.ports.scenarios import ScenarioRepository, ScenarioRow
from aiskra.shared.application import Query
from aiskra.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class ListScenarios(Query):
    status: str | None = None
    page: int = 1
    page_size: int = 30


@dataclass(frozen=True)
class ScenarioPage:
    items: list[ScenarioRow]
    total: int


class ListScenariosHandler:
    def __init__(self, repo: ScenarioRepository) -> None:
        self._repo = repo

    async def __call__(self, q: ListScenarios) -> ScenarioPage:
        if q.page < 1 or not 1 <= q.page_size <= 100:
            raise DomainError("Страница с 1, на странице 1–100", code="bad_page")
        items, total = await self._repo.page(status=q.status, limit=q.page_size, offset=(q.page - 1) * q.page_size)
        return ScenarioPage(items=items, total=total)


@dataclass(frozen=True, kw_only=True)
class GetScenario(Query):
    scenario_id: UUID


@dataclass(frozen=True)
class ScenarioView:
    id: UUID
    title: str
    status: str
    difficulty: int
    source: str
    card_type_code: str
    incident_type_code: str
    legend: dict[str, Any]
    reference_card: dict[str, Any]
    reference_dds: dict[str, Any]


class GetScenarioHandler:
    def __init__(self, repo: ScenarioRepository) -> None:
        self._repo = repo

    async def __call__(self, q: GetScenario) -> ScenarioView:
        s = await self._repo.get(q.scenario_id)
        if s is None:
            raise NotFoundError("Сценарий не найден", code="scenario_not_found")
        return ScenarioView(
            id=s.id,
            title=s.title,
            status=s.status.value,
            difficulty=s.difficulty,
            source=s.source,
            card_type_code=s.card_type_code,
            incident_type_code=s.incident_type_code,
            legend=s.legend,
            reference_card=s.reference_card,
            reference_dds=s.reference_dds,
        )
