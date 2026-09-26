"""Команда: вход по логину, паролю и номеру АРМ (экран входа АРМ-112, `img/instr/image1.png`).

Каждая попытка пишется в аудит. Неудачные попытки фиксируются в БД до ответа ошибкой,
иначе откат транзакции стёр бы и счётчик подбора пароля, и запись аудита.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import NoReturn

from aiskra.modules.identity.application.ports.auth import (
    AuthPolicy,
    PasswordHasher,
    SessionRepository,
    TokenIssuer,
    UserRepository,
)
from aiskra.modules.identity.domain.session import AuthSession
from aiskra.modules.identity.domain.user import User, normalize_number
from aiskra.shared.application import Clock, Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import AuthenticationError
from aiskra.shared.security import Principal

INVALID_CREDENTIALS = "Неверный логин или пароль"


@dataclass(frozen=True, kw_only=True)
class Login(Command):
    login: str
    password: str = field(repr=False)
    arm_number: str | None = None
    meta: RequestMeta = field(default_factory=RequestMeta)


@dataclass(frozen=True, kw_only=True)
class LoginResult:
    token: str = field(repr=False)
    expires_at: datetime
    principal: Principal


class LoginHandler:
    def __init__(
        self,
        users: UserRepository,
        sessions: SessionRepository,
        hasher: PasswordHasher,
        tokens: TokenIssuer,
        audit: AuditRecorder,
        uow: UnitOfWork,
        clock: Clock,
        policy: AuthPolicy,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._hasher = hasher
        self._tokens = tokens
        self._audit = audit
        self._uow = uow
        self._clock = clock
        self._policy = policy

    async def __call__(self, cmd: Login) -> LoginResult:
        arm_number = normalize_number(cmd.arm_number, what="Номер АРМ")
        login = cmd.login.strip().lower()
        now = self._clock.now()

        user = await self._users.get_by_login(login)
        if user is None:
            await self._hasher.burn(cmd.password)
            await self._reject(cmd, login, "Неизвестный логин", AuthenticationError(INVALID_CREDENTIALS))

        try:
            user.ensure_can_login(now)
        except AuthenticationError as exc:
            await self._reject(cmd, login, exc.message, exc, user=user)

        if not await self._hasher.verify(cmd.password, user.password_hash):
            locked = user.register_failed_login(now, self._policy.lockout)
            await self._users.save(user)
            if locked:
                await self._audit.record(
                    AuditEntry(
                        event=AuditEvent.ACCOUNT_LOCKED,
                        actor_login=login,
                        description=f"Вход закрыт до {user.locked_until:%d.%m.%Y %H:%M} UTC",
                        object_type="user",
                        object_id=str(user.id),
                        meta=cmd.meta,
                    )
                )
            await self._reject(cmd, login, "Неверный пароль", AuthenticationError(INVALID_CREDENTIALS), user=user)

        return await self._open_session(cmd, user, arm_number, now)

    async def _open_session(self, cmd: Login, user: User, arm_number: str | None, now: datetime) -> LoginResult:
        user.register_login(now)
        token = self._tokens.issue()
        session = AuthSession(
            user_id=user.id,
            token_hash=self._tokens.digest(token),
            created_at=now,
            expires_at=now + self._policy.session_ttl,
            arm_number=arm_number,
            ip=cmd.meta.ip,
            user_agent=cmd.meta.user_agent,
        )
        principal = Principal(
            user_id=user.id,
            session_id=session.id,
            login=user.login,
            full_name=user.full_name,
            role=user.role,
            operator_number=user.operator_number,
            arm_number=arm_number,
        )
        try:
            await self._users.save(user)
            await self._sessions.add(session)
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.LOGIN_SUCCEEDED,
                    actor=principal,
                    description=f"АРМ {arm_number}" if arm_number else "",
                    meta=cmd.meta,
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return LoginResult(token=token, expires_at=session.expires_at, principal=principal)

    async def _reject(
        self, cmd: Login, login: str, reason: str, error: AuthenticationError, *, user: User | None = None
    ) -> NoReturn:
        """Записать неудачную попытку, зафиксировать транзакцию и ответить ошибкой."""
        await self._audit.record(
            AuditEntry(
                event=AuditEvent.LOGIN_FAILED,
                actor_login=login,
                description=reason,
                object_type="user" if user else None,
                object_id=str(user.id) if user else None,
                meta=cmd.meta,
            )
        )
        await self._uow.commit()
        raise error
