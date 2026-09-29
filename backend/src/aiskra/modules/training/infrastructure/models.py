"""ORM training: сценарии, занятия, назначения (п. 0.2 — модель данных; логика — п. 3.2, 4.1, 4.2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from aiskra.platform.db import Base
from aiskra.platform.types import JsonType


class ScenarioModel(Base):
    """Сценарий: легенда заявителя + эталон карточки 112 + эталонные действия ДДС (specs/0.2 §5)."""

    __tablename__ = "scenarios"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)  # draft|review|approved|archived
    difficulty: Mapped[int] = mapped_column(Integer, default=1)  # 1–5
    roles: Mapped[list[str]] = mapped_column(JsonType, default=list)  # ["112", "dds"]
    card_type_code: Mapped[str | None] = mapped_column(String(64))
    incident_type_code: Mapped[str | None] = mapped_column(ForeignKey("dict_incident_types.code"), index=True)
    legend: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    reference_card: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    reference_dds: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    source: Mapped[str] = mapped_column(String(16), default="ai")  # ai | manual | trainee | ticket
    psy_profile: Mapped[str | None] = mapped_column(String(32))  # п. 3.7: закреплённый профиль заявителя
    review: Mapped[dict[str, Any] | None] = mapped_column(JsonType)  # п. 3.3: решения по разделам эталона
    version: Mapped[int] = mapped_column(Integer, default=1)
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TrainingSessionModel(Base):
    """Занятие: тип, категории, источник карточек, норматив (по умолчанию 30 с), пороги, темп очереди."""

    __tablename__ = "training_sessions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255))
    mode: Mapped[str] = mapped_column(String(16))  # cards_112 | dds_actions | mixed
    card_source: Mapped[str] = mapped_column(String(16), default="generated")  # generated | trainee | mixed
    settings: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="planned", index=True)  # planned|running|finished
    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    group_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("groups.id"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssignmentModel(Base):
    """Назначение обучающемуся: роль (112 / ДДС), профиль ДДС, сценарий или поток занятия."""

    __tablename__ = "assignments"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="CASCADE"), index=True
    )
    scenario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scenarios.id"))
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(8))  # 112 | dds
    dds_service_code: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="assigned")  # assigned|in_progress|done
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CallModel(Base):
    """Учебный звонок (п. 1.4, 2.3): входящий вызов заявителя, звонки ДДС старшему группы, заявителю, в службу."""

    __tablename__ = "training_calls"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    scenario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scenarios.id"))
    card_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("incident_cards.id", ondelete="SET NULL"), index=True)
    role: Mapped[str] = mapped_column(String(8))  # 112 | dds
    party: Mapped[str] = mapped_column(String(16))  # applicant | brigade | service
    direction: Mapped[str] = mapped_column(String(4))  # in | out
    service_code: Mapped[str | None] = mapped_column(String(64))
    target_service: Mapped[str | None] = mapped_column(String(64))
    aon: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(16), default="ringing")
    revealed: Mapped[list[str]] = mapped_column(JsonType, default=list)
    tone: Mapped[dict[str, Any] | None] = mapped_column(JsonType)  # состояние заявителя (п. 3.6)
    psy: Mapped[dict[str, Any] | None] = mapped_column(JsonType)  # п. 3.7: профиль и состояние заявителя
    ended_by: Mapped[str | None] = mapped_column(String(16))  # operator | party
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CallMessageModel(Base):
    __tablename__ = "training_call_messages"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    call_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("training_calls.id", ondelete="CASCADE"), index=True)
    speaker: Mapped[str] = mapped_column(String(16))  # operator | party | system
    text: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tone: Mapped[dict[str, Any] | None] = mapped_column(JsonType)  # снимок состояния у реплики собеседника (п. 3.6)
    via: Mapped[str | None] = mapped_column(String(12))  # у реплик оператора: text | voice | hands_free (п. 3.6)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JsonType)  # п. 3.7: действия, состояние, ремарки, голос


class MaterialModel(Base):
    """Учебный материал (п. 4.4): файл лежит в materials_dir под своим id, текст — здесь для поиска и промптов."""

    __tablename__ = "materials"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(16), index=True)
    filename: Mapped[str] = mapped_column(String(160))
    file_type: Mapped[str] = mapped_column(String(8))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    text: Mapped[str] = mapped_column(Text, default="")
    visible: Mapped[bool] = mapped_column(Boolean, default=True)
    use_in_prompts: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
