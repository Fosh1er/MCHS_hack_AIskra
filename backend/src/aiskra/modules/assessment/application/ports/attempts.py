"""Порты автооценки: попытка (карточка 112 или работа ДДС) — из incidents и training через адаптер
composition root; хранилище оценок."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from aiskra.modules.assessment.domain.psy_scoring import PsyAttempt
from aiskra.modules.assessment.domain.scoring import CallerFacts, StatusStep


@dataclass(frozen=True)
class Card112Attempt:
    card_id: UUID
    card_number: int
    author_id: UUID | None
    status: str
    data: dict[str, Any]
    services: list[str]
    processing_s: float | None
    reference: dict[str, Any] | None  # эталон сценария; None — карточка заведена без сценария
    legend_text: str  # что сообщил заявитель (для ИИ-судьи)
    asked_topics: set[str] | None  # темы вопросов оператора из разговора; None — разговора не было
    service_names: dict[str, str] = field(default_factory=dict)
    flag_names: dict[str, str] = field(default_factory=dict)
    caller: CallerFacts | None = None  # как менялось состояние ИИ-заявителя (п. 3.6); None — без состояния
    psy: PsyAttempt | None = None  # п. 3.7: разговор с заявителем, у которого был психологический профиль


@dataclass(frozen=True)
class DdsAttempt:
    card_id: UUID
    card_number: int
    service_code: str
    history: list[StatusStep]
    added_at: datetime | None
    reference: dict[str, Any] | None
    calls: list[str]  # стороны звонков по карточке: brigade | applicant | service
    actor_ids: set[UUID]  # кто ставил статусы
    psy: PsyAttempt | None = None  # п. 3.7: звонок заявителю из ДДС с психологическим профилем


class AttemptSource(Protocol):
    async def card_112(self, card_id: UUID) -> Card112Attempt | None: ...

    async def dds(self, card_id: UUID, service_code: str) -> DdsAttempt | None: ...


@dataclass(frozen=True)
class AssessmentRecord:
    id: UUID
    card_id: UUID
    student_id: UUID | None
    role: str
    service_code: str | None
    score: float
    passed: bool
    grader: str
    details: dict[str, Any]
    created_at: datetime | None = None


class AssessmentRepository(Protocol):
    async def add(self, record: AssessmentRecord) -> None: ...

    async def latest(self, card_id: UUID, role: str, service_code: str | None) -> AssessmentRecord | None: ...

    async def recent(self, limit: int) -> list[AssessmentRecord]: ...
