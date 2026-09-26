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
