"""Команда: администратор задаёт новый пароль. Все сессии пользователя отзываются, блокировка по попыткам снимается."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from aiskra.modules.identity.application.commands._common import load_user
from aiskra.modules.identity.application.ports.auth import PasswordHasher, SessionRepository, UserRepository
from aiskra.modules.identity.domain.user import validate_password
from aiskra.shared.application import Clock, Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.security import Principal


@dataclass(frozen=True, kw_only=True)
class ResetPassword(Command):
    actor: Principal
    user_id: UUID
    new_password: str = field(repr=False)
    meta: RequestMeta = field(default_factory=RequestMeta)


class ResetPasswordHandler:
    def __init__(
        self,
        users: UserRepository,
        sessions: SessionRepository,
        hasher: PasswordHasher,
        audit: AuditRecorder,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._hasher = hasher
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def __call__(self, cmd: ResetPassword) -> None:
        user = await load_user(self._users, cmd.user_id)
        validate_password(cmd.new_password, login=user.login)
        user.set_password_hash(await self._hasher.hash(cmd.new_password))
        try:
            await self._users.save(user)
            await self._sessions.revoke_all_for_user(user.id, self._clock.now())
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.PASSWORD_RESET,
                    actor=cmd.actor,
                    description=user.login,
                    object_type="user",
                    object_id=str(user.id),
                    meta=cmd.meta,
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
