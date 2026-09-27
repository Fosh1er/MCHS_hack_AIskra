"""Порт отчёта по занятию (п. 4.3): занятие, участники и карточки — из training и incidents через адаптер."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True)
class ReportParticipant:
    student_id: UUID
    full_name: str
    role: str
    service_code: str | None


@dataclass(frozen=True)
class ReportCard:
    card_id: UUID
    number: int
    author_id: UUID | None
    origin: str
    status: str
    saved_at: datetime | None
    processing_s: float | None
    card_types: list[str]
    services: dict[str, str] = field(default_factory=dict)  # код службы → текущий статус
    # аналитика преподавателя: что отрабатывалось (по сценарию — истина, иначе выбор оператора)
    incident_type: str | None = None
    incident_group: int | None = None
    difficulty: int | None = None
    reactions: dict[str, float] = field(default_factory=dict)  # код службы → с от поступления до решения ДДС


@dataclass(frozen=True)
class SessionFacts:
    session_id: UUID
    teacher_id: UUID
    title: str
    mode: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    settings: dict[str, Any]
    participants: list[ReportParticipant]
    cards: list[ReportCard]


class SessionFactsSource(Protocol):
    async def session(self, session_id: UUID) -> SessionFacts | None: ...

    async def teacher_sessions(self, teacher_id: UUID, since: datetime | None = None) -> list[UUID]:
        """Занятия преподавателя (начатые), от новых к старым; `since` — начатые не раньше."""
        ...


class ScenarioBank(Protocol):
    """Банк сценариев глазами аналитики: названия групп классификатора и сколько утверждённых сценариев есть."""

    async def group_titles(self) -> dict[int, str]: ...

    async def approved_count(self, groups: list[int], difficulty: int | None) -> dict[int, int]:
        """Число утверждённых сценариев по группам; `difficulty` — только этой сложности."""
        ...
