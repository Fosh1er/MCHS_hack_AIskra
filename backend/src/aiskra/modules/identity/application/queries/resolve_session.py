"""Запрос: по токену из cookie найти действующую сессию и вернуть субъекта доступа.

Выполняется на каждом защищённом запросе, поэтому роль и статус читаются из БД каждый раз:
блокировка и смена роли действуют сразу, без повторного входа.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aiskra.modules.identity.application.ports.auth import TokenIssuer
from aiskra.modules.identity.application.ports.reader import SessionReader
from aiskra.modules.identity.domain.user import UserStatus
from aiskra.shared.application import Clock, Query
from aiskra.shared.errors import AuthenticationError
from aiskra.shared.security import Principal, Role

SESSION_REQUIRED = "Требуется вход в систему"


@dataclass(frozen=True, kw_only=True)
class ResolveSession(Query):
    token: str | None = field(repr=False)


class ResolveSessionHandler:
    def __init__(self, sessions: SessionReader, tokens: TokenIssuer, clock: Clock) -> None:
        self._sessions = sessions
        self._tokens = tokens
        self._clock = clock

    async def __call__(self, query: ResolveSession) -> Principal:
        if not query.token:
            raise AuthenticationError(SESSION_REQUIRED)
        view = await self._sessions.find_by_token_hash(self._tokens.digest(query.token))
        if view is None or view.revoked_at is not None:
            raise AuthenticationError(SESSION_REQUIRED)
        if self._clock.now() >= view.expires_at:
            raise AuthenticationError("Сессия истекла, войдите снова", code="session_expired")
        if view.user_status != UserStatus.ACTIVE:
            raise AuthenticationError("Учётная запись заблокирована", code="account_blocked")
        return Principal(
            user_id=view.user_id,
            session_id=view.session_id,
            login=view.login,
            full_name=view.full_name,
            role=Role(view.role),
            operator_number=view.operator_number,
            arm_number=view.arm_number,
        )
