"""ORM incidents: карточка 112, службы карточки и их статусы, очередь ДДС (п. 0.2; логика — п. 1.x, 2.x)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, false, func
from sqlalchemy.orm import Mapped, mapped_column

from aiskra.platform.db import Base
from aiskra.platform.types import JsonType


class IncidentCardModel(Base):
    """Карточка происшествия. payload — структура АРМ-112 (specs/0.2 §4, domain/card.py);
    часто фильтруемые поля продублированы колонками для журнала."""

    __tablename__ = "incident_cards"
    __table_args__ = (
        Index("ix_incident_cards_author_opened", "author_id", "opened_at"),
        Index("ix_incident_cards_opened", "opened_at"),
        Index("ix_incident_cards_saved", "saved_at"),
    )  # п. 6.1, миграция 0011
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    number: Mapped[int] = mapped_column(BigInteger, unique=True)  # «Происшествие 36814845»
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("training_sessions.id"), index=True)
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assignments.id"), index=True)
    scenario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scenarios.id"))
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    operator_number: Mapped[str | None] = mapped_column(String(16))  # «Опер.» в шапке карточки и журнале
    arm_number: Mapped[str | None] = mapped_column(String(16))  # «АРМ» — номер, введённый при входе
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
    paused_ms: Mapped[int | None] = mapped_column(Integer)  # п. 5.3: пауза таймера на обучение интерфейсу
    pause_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # пауза идёт сейчас
    is_emergency: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())  # ЧС
    is_incident: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())  # ЧП
    worked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    search_key: Mapped[str | None] = mapped_column(Text)  # номер, адрес, телефоны, заявитель, описание (п. 1.3)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CardServiceModel(Base):
    """Служба, назначенная на карточку (авто по классификатору или вручную)."""

    __tablename__ = "card_services"
    __table_args__ = (
        Index("ix_card_services_service_status", "service_code", "current_status", "card_saved_at"),
        Index("ix_card_services_service_saved", "service_code", "card_saved_at", "card_number"),
    )  # п. 6.1, миграция 0011
    card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incident_cards.id", ondelete="CASCADE"), primary_key=True)
    service_code: Mapped[str] = mapped_column(ForeignKey("dict_services.code"), primary_key=True)
    is_main: Mapped[bool] = mapped_column(Boolean, default=False)
    added_by: Mapped[str] = mapped_column(String(16), default="auto")  # auto | manual | external (ВИС)
    service_type: Mapped[str | None] = mapped_column(Text)  # «Класс.:» у службы
    current_status: Mapped[str] = mapped_column(String(32), default="added")  # enums.service_status
    # копия времени сохранения и номера карточки (6.1): журнал ДДС сортирует и считает по одному индексу службы,
    # без поиска каждой карточки по ключу; пишется один раз — строки служб создаются при сохранении карточки
    card_saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    card_number: Mapped[int | None] = mapped_column(BigInteger)
    # п. 5.3: пауза таймера решения ДДС на подсказки по экрану — не входит во время реакции
    paused_ms: Mapped[int | None] = mapped_column(Integer)
    pause_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CardServiceStatusModel(Base):
    """История статусов службы по карточке (нижние поля карточки ДДС)."""

    __tablename__ = "card_service_statuses"
    __table_args__ = (
        Index("ix_card_service_statuses_card_service", "card_id", "service_code", "at"),
    )  # п. 6.1, миграция 0011
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


class CardWorkoutModel(Base):
    """Отработка (`image70`): звонок оператора в службу или другому адресату после сохранения карточки."""

    __tablename__ = "card_workouts"
    __table_args__ = (Index("ix_card_workouts_card_service", "card_id", "service_code"),)  # п. 6.1, миграция 0011
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incident_cards.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    operator_number: Mapped[str | None] = mapped_column(String(16))
    service_code: Mapped[str | None] = mapped_column(ForeignKey("dict_services.code"))
    target: Mapped[str] = mapped_column(String(255), default="")
    called_to: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    receiver: Mapped[str] = mapped_column(String(255), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
