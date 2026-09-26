"""Порты занятий (п. 4.2): хранилище, справочник обучающихся, системные карточки и мониторинг — последние два
через адаптеры composition root (карточки и оценки живут в incidents и assessment)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from aiskra.modules.training.domain.scenario import Scenario
from aiskra.modules.training.domain.session import TrainingSession


class SessionRepository(Protocol):
    async def add(self, session: TrainingSession) -> None: ...

    async def get(self, session_id: UUID) -> TrainingSession | None: ...

    async def save(self, session: TrainingSession) -> None: ...

    async def page(self, *, teacher_id: UUID | None, limit: int, offset: int) -> tuple[list[TrainingSession], int]: ...

    async def running_for_student(self, student_id: UUID) -> TrainingSession | None: ...


@dataclass(frozen=True)
class StudentRow:
    id: UUID
    login: str
    full_name: str
    operator_number: str | None


class StudentDirectory(Protocol):
    async def students(self) -> list[StudentRow]: ...

    async def names(self, ids: list[UUID]) -> dict[UUID, StudentRow]: ...


class SystemCards(Protocol):
    """Карточка 112 «от системы» по эталону сценария — поступает в очередь ДДС обучающегося (ТЗ сценарий 3)."""

    async def create_from_scenario(
        self, scenario: Scenario, *, extra_service: str | None, session_id: UUID, author_id: UUID
    ) -> UUID: ...

    async def waiting(self, service_code: str, session_id: UUID) -> tuple[int, datetime | None]:
        """Сколько карточек занятия ждут решения этой ДДС и когда поступила последняя."""
        ...


@dataclass(frozen=True)
class ParticipantProgress:
    student_id: UUID
    cards_done: int = 0
    current_card: int | None = None  # номер карточки в работе
    current_label: str = ""
    current_since: datetime | None = None  # с какого момента идёт таймер текущей карточки
    waiting: int = 0  # ДДС: карточек в очереди
    avg_score: float | None = None
    errors: int = 0
    last_errors: list[str] = field(default_factory=list)


class SessionMonitorSource(Protocol):
    async def progress(self, session: TrainingSession) -> list[ParticipantProgress]: ...
