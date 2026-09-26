"""Запросы банка сценариев (п. 3.2): список и сценарий целиком — для проверки и утверждения преподавателем (4.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from aiskra.modules.training.application.ports.scenarios import ScenarioRepository, ScenarioRow
from aiskra.modules.training.domain.actors import applicant_reply
from aiskra.shared.application import Query
from aiskra.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class ListScenarios(Query):
    status: str | None = None
    difficulty: int | None = None
    card_type: str | None = None
    source: str | None = None
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
        items, total = await self._repo.page(
            status=q.status,
            difficulty=q.difficulty,
            card_type=q.card_type,
            source=q.source,
            limit=q.page_size,
            offset=(q.page - 1) * q.page_size,
        )
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


PREVIEW_QUESTIONS = [
    "Служба 112, что у вас случилось?",
    "Назовите адрес.",
    "Подъезд, этаж, квартира?",
    "Есть пострадавшие?",
    "Как вас зовут?",
    "Кем вы приходитесь пострадавшему?",
]


@dataclass(frozen=True)
class PreviewItem:
    question: str
    answer: str
    reference: str  # что оператор должен занести в карточку


@dataclass(frozen=True, kw_only=True)
class PreviewScenario(Query):
    """Предпросмотр (ТЗ сценарий 1): вопросы оператора, ответы заявителя по легенде и «правильное» по эталону."""

    scenario_id: UUID


class PreviewScenarioHandler:
    def __init__(self, repo: ScenarioRepository) -> None:
        self._repo = repo

    async def __call__(self, q: PreviewScenario) -> list[PreviewItem]:
        s = await self._repo.get(q.scenario_id)
        if s is None:
            raise NotFoundError("Сценарий не найден", code="scenario_not_found")
        ref = s.reference_card
        a = ref.get("address") or {}
        victims = ref.get("victims") or {}
        signs = ", ".join((ref.get("questionnaire") or {}).get(s.card_type_code, {}).values())
        expected = [
            f"Тип: {ref.get('final_type')}; признаки: {signs}",
            f"Адрес: {a.get('street')}, {a.get('house')} ({a.get('district') or 'район —'})",
            f"Этаж {a.get('floor') or '—'}, квартира {a.get('flat') or '—'}",
            f"Пострадавшие: {'есть, ' + str(victims.get('count')) if victims.get('has') else 'нет'}",
            f"ФИО заявителя: {(ref.get('applicant') or {}).get('name')}",
            f"Статус заявителя: {(ref.get('applicant') or {}).get('status')}",
        ]
        revealed: list[str] = []
        out = []
        for question, exp in zip(PREVIEW_QUESTIONS, expected, strict=True):
            r = applicant_reply(s.legend, question, revealed)
            revealed = r.revealed
            out.append(PreviewItem(question=question, answer=r.text, reference=exp))
        return out
