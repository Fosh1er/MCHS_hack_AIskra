"""Порт хранилища отзывов преподавателя по занятию (п. 4.7): один действующий отзыв на пару «занятие + обучающийся»."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True)
class FeedbackRecord:
    session_id: UUID
    student_id: UUID
    teacher_id: UUID
    session_title: str  # копия на момент сохранения: история обучающегося не ходит в модуль training
    session_started_at: datetime | None
    text: str
    # focus — ключи критериев «подтянуть», criteria — средние тогда (для сравнения в следующем отзыве);
    # draft — с чего начал преподаватель: {source: ai | rules | manual, model, similarity}
    details: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FeedbackStore(Protocol):
    async def get(self, session_id: UUID, student_id: UUID) -> FeedbackRecord | None: ...

    async def for_session(self, session_id: UUID) -> dict[UUID, FeedbackRecord]:
        """Отзывы занятия по обучающимся."""
        ...

    async def for_student(self, student_id: UUID) -> list[FeedbackRecord]:
        """Все отзывы обучающегося, от новых занятий к старым."""
        ...

    async def save(self, record: FeedbackRecord) -> FeedbackRecord:
        """Создаёт отзыв или заменяет текст действующего."""
        ...
