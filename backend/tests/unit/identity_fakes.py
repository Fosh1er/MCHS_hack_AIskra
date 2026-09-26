"""Фейки портов identity для unit-тестов обработчиков (без БД)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from aiskra.modules.identity.domain.session import AuthSession
from aiskra.modules.identity.domain.user import User, UserStatus
from aiskra.shared.audit import AuditEntry
from aiskra.shared.security import Role


class FakeUsers:
    def __init__(self, *users: User) -> None:
        self.by_id = {u.id: u for u in users}

    async def get(self, user_id: UUID) -> User | None:
        return self.by_id.get(user_id)

    async def get_by_login(self, login: str) -> User | None:
        return next((u for u in self.by_id.values() if u.login == login), None)

    async def add(self, user: User) -> None:
        self.by_id[user.id] = user

    async def save(self, user: User) -> None:
        self.by_id[user.id] = user

    async def count_active_admins(self) -> int:
        return sum(1 for u in self.by_id.values() if u.role is Role.ADMIN and u.status is UserStatus.ACTIVE)


class FakeSessions:
    def __init__(self) -> None:
        self.by_id: dict[UUID, AuthSession] = {}

    async def get(self, session_id: UUID) -> AuthSession | None:
        return self.by_id.get(session_id)

    async def add(self, session: AuthSession) -> None:
        self.by_id[session.id] = session

    async def save(self, session: AuthSession) -> None:
        self.by_id[session.id] = session

    async def revoke_all_for_user(self, user_id: UUID, now: datetime) -> int:
        active = [s for s in self.by_id.values() if s.user_id == user_id and s.revoked_at is None]
        for s in active:
            s.revoke(now)
        return len(active)


class PlainHasher:
    """«Хеш» = префикс + пароль: проверяем логику обработчиков, а не криптографию."""

    def __init__(self) -> None:
        self.burned = 0

    async def hash(self, password: str) -> str:
        return f"plain:{password}"

    async def verify(self, password: str, password_hash: str) -> bool:
        return password_hash == f"plain:{password}"

    async def burn(self, password: str) -> None:
        self.burned += 1


class CountingTokens:
    def __init__(self) -> None:
        self.n = 0

    def issue(self) -> str:
        self.n += 1
        return f"token-{self.n}"

    def digest(self, token: str) -> str:
        return f"sha:{token}"


class FakeAudit:
    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    async def record(self, entry: AuditEntry) -> None:
        self.entries.append(entry)

    @property
    def events(self) -> list[str]:
        return [e.event.value for e in self.entries]


class FakeUow:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FixedClock:
    def __init__(self, now: datetime | None = None) -> None:
        self.current = now or datetime(2026, 9, 26, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, **kw: float) -> None:
        self.current += timedelta(**kw)
