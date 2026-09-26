"""ORM incidents: карточка 112, службы карточки и их статусы, очередь ДДС (п. 0.2; логика — п. 1.x, 2.x)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from aiskra.platform.db import Base
from aiskra.platform.types import JsonType


class IncidentCardModel(Base):
    """Карточка происшествия. payload — структура АРМ-112 (specs/0.2 §4, domain/card.py);
    часто фильтруемые поля продублированы колонками для журнала."""

    __tablename__ = "incident_cards"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    number: Mapped[int] = mapped_column(BigInteger, unique=True)  # «Происшествие 36814845»
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("training_sessions.id"), index=True)
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assignments.id"), index=True)
    scenario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scenarios.id"))
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    origin: Mapped[str] = mapped_column(String(16), default="student")  # student | system | scenario
    channel: Mapped[str | None] = mapped_column(String(32))  # сообщение/звонок/СМС
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)  # draft + enums.card_status
    card_type_codes: Mapped[list[str]] = mapped_column(JsonType, default=list)
    incident_type_codes: Mapped[list[str]] = mapped_column(JsonType, default=list)
    okrug_code: Mapped[str | None] = mapped_column(String(8))
    district_code: Mapped[str | None] = mapped_column(String(64))
    address_text: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    has_victims: Mapped[bool] = mapped_column(Boolean, default=False)
    victims_count: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_ms: Mapped[int | None] = mapped_column(Integer)  # таймер карточки
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CardServiceModel(Base):
    """Служба, назначенная на карточку (авто по классификатору или вручную)."""

    __tablename__ = "card_services"
    card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incident_cards.id", ondelete="CASCADE"), primary_key=True)
    service_code: Mapped[str] = mapped_column(ForeignKey("dict_services.code"), primary_key=True)
    is_main: Mapped[bool] = mapped_column(Boolean, default=False)
    added_by: Mapped[str] = mapped_column(String(16), default="auto")  # auto | manual | external (ВИС)
    service_type: Mapped[str | None] = mapped_column(Text)  # «Класс.:» у службы
    current_status: Mapped[str] = mapped_column(String(32), default="added")  # enums.service_status


class CardServiceStatusModel(Base):
    """История статусов службы по карточке (нижние поля карточки ДДС)."""

    __tablename__ = "card_service_statuses"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incident_cards.id", ondelete="CASCADE"), index=True)
    service_code: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    order_no: Mapped[str | None] = mapped_column(String(32))  # «Номер наряда»
    comment: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DdsQueueItemModel(Base):
    """Карточка в очереди конкретного обучающегося-ДДС. Таймер ожидания — от enqueued_at (#709)."""

    __tablename__ = "dds_queue_items"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incident_cards.id", ondelete="CASCADE"), index=True)
    dds_service_code: Mapped[str] = mapped_column(ForeignKey("dict_services.code"))
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assignments.id"), index=True)
    state: Mapped[str] = mapped_column(String(16), default="waiting")  # waiting | in_work | done | rejected
    enqueued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
