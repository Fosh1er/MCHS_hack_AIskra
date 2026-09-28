"""ORM identity: пользователи, сессии входа, группы (модель — п. 0.2; вход, права и сессии — п. 0.3)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from aiskra.platform.db import Base
from aiskra.platform.types import JsonType


class UserModel(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    login: Mapped[str] = mapped_column(String(64), unique=True)
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), index=True)  # admin | teacher | student
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | blocked
    password_hash: Mapped[str | None] = mapped_column(String(255))
    operator_number: Mapped[str | None] = mapped_column(String(16))  # «Опер. NNNN» в карточке
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    search_key: Mapped[str] = mapped_column(String(320), default="", server_default="")  # логин + ФИО для поиска
    onboarding: Mapped[dict[str, Any] | None] = mapped_column(JsonType)  # п. 5.3: {dismissed, seen[]}; NULL — новый


class AuthSessionModel(Base):
    """Сессия входа (ADR-0010). Токен хранится только как SHA-256."""

    __tablename__ = "auth_sessions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    arm_number: Mapped[str | None] = mapped_column(String(16))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GroupModel(Base):
    __tablename__ = "groups"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GroupMemberModel(Base):
    __tablename__ = "group_members"
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    member_role: Mapped[str] = mapped_column(String(16), default="student")  # student | teacher
    dds_service_code: Mapped[str | None] = mapped_column(String(64))  # профиль ДДС (ролевая модель ленты)
