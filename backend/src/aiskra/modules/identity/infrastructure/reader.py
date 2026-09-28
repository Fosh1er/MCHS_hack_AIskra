"""SQL-реализации портов чтения identity."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.identity.application.ports.reader import SessionView, UserFilter, UserListItem
from aiskra.modules.identity.infrastructure.models import AuthSessionModel, UserModel
from aiskra.platform.types import as_utc
from aiskra.shared.text import search_key


class SqlSessionReader:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def find_by_token_hash(self, token_hash: str) -> SessionView | None:
        stmt = (
            select(AuthSessionModel, UserModel)
            .join(UserModel, UserModel.id == AuthSessionModel.user_id)
            .where(AuthSessionModel.token_hash == token_hash)
        )
        found = (await self._s.execute(stmt)).first()
        if found is None:
            return None
        sess, user = found
        expires_at = as_utc(sess.expires_at)
        assert expires_at is not None
        return SessionView(
            session_id=sess.id,
            expires_at=expires_at,
            revoked_at=as_utc(sess.revoked_at),
            arm_number=sess.arm_number,
            user_id=user.id,
            login=user.login,
            full_name=user.full_name,
            role=user.role,
            user_status=user.status,
            operator_number=user.operator_number,
        )


class SqlUserReader:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list(self, flt: UserFilter) -> tuple[list[UserListItem], int]:
        conditions: list[ColumnElement[bool]] = []
        if flt.q:
            conditions.append(UserModel.search_key.like(f"%{search_key(flt.q)}%"))
        if flt.role:
            conditions.append(UserModel.role == flt.role)
        if flt.status:
            conditions.append(UserModel.status == flt.status)
        total = int(
            (await self._s.execute(select(func.count()).select_from(UserModel).where(*conditions))).scalar_one()
        )
        rows = (
            await self._s.execute(
                select(UserModel).where(*conditions).order_by(UserModel.login).limit(flt.limit).offset(flt.offset)
            )
        ).scalars()
        items = [
            UserListItem(
                id=r.id,
                login=r.login,
                full_name=r.full_name,
                role=r.role,
                status=r.status,
                operator_number=r.operator_number,
                locked_until=as_utc(r.locked_until),
                last_login_at=as_utc(r.last_login_at),
                created_at=as_utc(r.created_at) or r.created_at,
            )
            for r in rows
        ]
        return items, total


class SqlOnboardingReader:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def onboarding(self, user_id: UUID) -> dict[str, Any] | None:
        stmt = select(UserModel.onboarding).where(UserModel.id == user_id)
        value: dict[str, Any] | None = (await self._s.execute(stmt)).scalar_one_or_none()
        return value
