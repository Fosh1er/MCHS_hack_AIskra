"""ORM assessment: события действий, оценки, экспертные правки, отчёты (п. 0.2; логика — п. 3.4, 4.3)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from aiskra.platform.db import Base
from aiskra.platform.types import JsonType


class ActionEventModel(Base):
    """Событие действия обучающегося — основа тайминга, оценки и разбора (append-only)."""

    __tablename__ = "action_events"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    client_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)  # идемпотентность досылки
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("training_sessions.id"), index=True)
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assignments.id"), index=True)
    card_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("incident_cards.id"), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    type: Mapped[str] = mapped_column(String(64))  # card.opened, field.changed, service.status_set, call.started…
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    client_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    server_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class AssessmentModel(Base):
    """Оценка попытки/карточки: итог, разбивка по критериям и ошибкам, уверенность."""

    __tablename__ = "assessments"
    __table_args__ = (Index("ix_assessments_card_created", "card_id", "created_at"),)  # п. 6.1, миграция 0011
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assignments.id"), index=True)
    card_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("incident_cards.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="preliminary")  # preliminary|final|pending_ai|needs_review
    score: Mapped[float | None] = mapped_column(Float)
    details: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)  # критерии, ошибки, отклонение от норматива
    confidence: Mapped[float | None] = mapped_column(Float)
    grader: Mapped[str] = mapped_column(String(64), default="rules")  # rules | rules+llm | expert
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExpertOverrideModel(Base):
    """Экспертная правка оценки преподавателем — обязательна причина (ТЗ: изменение оценки через аудит)."""

    __tablename__ = "expert_overrides"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    changes: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReportModel(Base):
    """Сформированный отчёт (по занятию, обучающемуся, группе) и путь к файлу экспорта."""

    __tablename__ = "reports"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("training_sessions.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # session | student | group
    format: Mapped[str] = mapped_column(String(8), default="json")  # json | csv | pdf | xlsx
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    file_path: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
