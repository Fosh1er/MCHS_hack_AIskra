"""ORM audit: журнал аудита. Колонки повторяют раздел «Аудит» АРМ-112 (Карточка, Опер., ФИО, Дата, Время,
Событие, Описание) + технические поля. Хранение ≥ 6 месяцев (ТЗ)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from aiskra.platform.db import Base
from aiskra.platform.types import JsonType


class AuditLogModel(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    card_number: Mapped[int | None] = mapped_column(BigInteger, index=True)  # «Карточка»
    operator_number: Mapped[str | None] = mapped_column(String(16))  # «Опер.»
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    actor_name: Mapped[str | None] = mapped_column(String(255))  # «ФИО»
    actor_login: Mapped[str | None] = mapped_column(String(64), index=True)
    actor_role: Mapped[str | None] = mapped_column(String(16))
    actor_key: Mapped[str | None] = mapped_column(String(320))  # ФИО + логин для поиска «по оператору»
    description_key: Mapped[str | None] = mapped_column(Text)  # описание для поиска
    arm_number: Mapped[str | None] = mapped_column(String(16))
    event: Mapped[str] = mapped_column(String(64), index=True)  # «Событие» (код)
    description: Mapped[str | None] = mapped_column(Text)  # «Описание»
    object_type: Mapped[str | None] = mapped_column(String(32))
    object_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
    data: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
