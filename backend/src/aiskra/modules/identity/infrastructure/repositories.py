"""SQL-репозитории identity: отображение ORM ↔ домен (домен не знает об ORM)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.identity.domain.onboarding import Onboarding
from aiskra.modules.identity.domain.session import AuthSession
from aiskra.modules.identity.domain.user import User, UserStatus
from aiskra.modules.identity.infrastructure.models import AuthSessionModel, UserModel
from aiskra.platform.types import as_utc
from aiskra.shared.security import Role
from aiskra.shared.text import search_key


def _to_user(row: UserModel) -> User:
    return User(
        id=row.id,
        login=row.login,
        full_name=row.full_name,
        role=Role(row.role),
        password_hash=row.password_hash or "",
        status=UserStatus(row.status),
        operator_number=row.operator_number,
        failed_attempts=row.failed_attempts or 0,
        locked_until=as_utc(row.locked_until),
        last_login_at=as_utc(row.last_login_at),
        onboarding=Onboarding.from_json(row.onboarding),
    )


def _fill_user(row: UserModel, user: User) -> None:
    row.login = user.login
    row.full_name = user.full_name
    row.role = user.role.value
    row.password_hash = user.password_hash
    row.status = user.status.value
    row.operator_number = user.operator_number
    row.failed_attempts = user.failed_attempts
    row.locked_until = user.locked_until
    row.last_login_at = user.last_login_at
    row.search_key = search_key(user.login, user.full_name)
    row.onboarding = user.onboarding.to_json()


class SqlUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, user_id: UUID) -> User | None:
        row = await self._s.get(UserModel, user_id)
        return _to_user(row) if row else None

    async def get_by_login(self, login: str) -> User | None:
        row = (await self._s.execute(select(UserModel).where(UserModel.login == login))).scalar_one_or_none()
        return _to_user(row) if row else None

    async def add(self, user: User) -> None:
        row = UserModel(id=user.id)
        _fill_user(row, user)
        self._s.add(row)
        await self._s.flush()

    async def save(self, user: User) -> None:
        row = await self._s.get(UserModel, user.id)
        if row is None:
            raise LookupError(f"Пользователь {user.id} не найден при сохранении")
        _fill_user(row, user)
        await self._s.flush()

    async def count_active_admins(self) -> int:
        stmt = select(func.count()).where(
            UserModel.role == Role.ADMIN.value, UserModel.status == UserStatus.ACTIVE.value
        )
        return int((await self._s.execute(stmt)).scalar_one())


def _to_session(row: AuthSessionModel) -> AuthSession:
    created_at, expires_at = as_utc(row.created_at), as_utc(row.expires_at)
    assert created_at is not None and expires_at is not None
    return AuthSession(
        id=row.id,
        user_id=row.user_id,
        token_hash=row.token_hash,
        created_at=created_at,
        expires_at=expires_at,
        arm_number=row.arm_number,
        ip=row.ip,
        user_agent=row.user_agent,
        revoked_at=as_utc(row.revoked_at),
    )


class SqlSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, session_id: UUID) -> AuthSession | None:
        row = await self._s.get(AuthSessionModel, session_id)
        return _to_session(row) if row else None

    async def add(self, session: AuthSession) -> None:
        self._s.add(
            AuthSessionModel(
                id=session.id,
                user_id=session.user_id,
                token_hash=session.token_hash,
                arm_number=session.arm_number,
                ip=session.ip,
                user_agent=(session.user_agent or "")[:255] or None,
                created_at=session.created_at,
                expires_at=session.expires_at,
                revoked_at=session.revoked_at,
            )
        )
        await self._s.flush()

    async def save(self, session: AuthSession) -> None:
        await self._s.execute(
            update(AuthSessionModel).where(AuthSessionModel.id == session.id).values(revoked_at=session.revoked_at)
        )

    async def revoke_all_for_user(self, user_id: UUID, now: datetime) -> int:
        result = await self._s.execute(
            update(AuthSessionModel)
            .where(AuthSessionModel.user_id == user_id, AuthSessionModel.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        return int(getattr(result, "rowcount", 0) or 0)
