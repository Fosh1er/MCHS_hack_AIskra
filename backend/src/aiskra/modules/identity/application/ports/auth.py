"""Порты модуля identity: хранилища пользователей и сессий, хеширование паролей, токены."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from aiskra.modules.identity.domain.session import AuthSession
from aiskra.modules.identity.domain.user import LockoutPolicy, User


@dataclass(frozen=True, kw_only=True)
class AuthPolicy:
    """Параметры входа из настроек (AISKRA_SESSION_TTL_HOURS, AISKRA_LOGIN_*)."""

    session_ttl: timedelta = timedelta(hours=24)
    lockout: LockoutPolicy = field(default_factory=LockoutPolicy)


class UserRepository(Protocol):
    async def get(self, user_id: UUID) -> User | None: ...

    async def get_by_login(self, login: str) -> User | None: ...

    async def add(self, user: User) -> None: ...

    async def save(self, user: User) -> None: ...

    async def count_active_admins(self) -> int: ...


class SessionRepository(Protocol):
    async def get(self, session_id: UUID) -> AuthSession | None: ...

    async def add(self, session: AuthSession) -> None: ...

    async def save(self, session: AuthSession) -> None: ...

    async def revoke_all_for_user(self, user_id: UUID, now: datetime) -> int:
        """Отозвать все действующие сессии пользователя. Возвращает их число."""
        ...


class PasswordHasher(Protocol):
    async def hash(self, password: str) -> str: ...

    async def verify(self, password: str, password_hash: str) -> bool: ...

    async def burn(self, password: str) -> None:
        """Потратить столько же времени, сколько проверка пароля (вход с несуществующим логином
        не должен отвечать быстрее — иначе логины перебираются по времени ответа)."""
        ...


class TokenIssuer(Protocol):
    def issue(self) -> str:
        """Новый секретный токен сессии (уходит клиенту в cookie)."""
        ...

    def digest(self, token: str) -> str:
        """Необратимый отпечаток токена (хранится в БД)."""
        ...


class LoginThrottle(Protocol):
    """Ограничение неудачных входов с одного адреса (п. 6.2) — в дополнение к блокировке учётки."""

    def check(self, key: str) -> None:
        """Бросает TooManyRequestsError, если с адреса слишком много неудачных попыток."""
        ...

    def failed(self, key: str) -> None: ...

    def succeeded(self, key: str) -> None: ...
