"""Порты чтения identity (CQRS-lite: запросы читают сразу в DTO, минуя агрегаты)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, kw_only=True)
class SessionView:
    """Сессия вместе с данными пользователя — всё, что нужно для проверки запроса одной выборкой."""

    session_id: UUID
    expires_at: datetime
    revoked_at: datetime | None
    arm_number: str | None
    user_id: UUID
    login: str
    full_name: str
    role: str
    user_status: str
    operator_number: str | None


@dataclass(frozen=True, kw_only=True)
class UserListItem:
    id: UUID
    login: str
    full_name: str
    role: str
    status: str
    operator_number: str | None
    locked_until: datetime | None
    last_login_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, kw_only=True)
class UserFilter:
    q: str = ""
    role: str | None = None
    status: str | None = None
    limit: int = 50
    offset: int = 0


class SessionReader(Protocol):
    async def find_by_token_hash(self, token_hash: str) -> SessionView | None: ...


class UserReader(Protocol):
    async def list(self, flt: UserFilter) -> tuple[list[UserListItem], int]: ...
