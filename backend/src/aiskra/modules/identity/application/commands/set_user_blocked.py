"""Команда: заблокировать или разблокировать пользователя. Блокировка сразу отзывает все его сессии."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from aiskra.modules.identity.application.commands._common import ensure_admin_remains, load_user
from aiskra.modules.identity.application.ports.auth import SessionRepository, UserRepository
from aiskra.shared.application import Clock, Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import DomainError
from aiskra.shared.security import Principal


@dataclass(frozen=True, kw_only=True)
class SetUserBlocked(Command):
    actor: Principal
    user_id: UUID
    blocked: bool
    reason: str = ""
    meta: RequestMeta = field(default_factory=RequestMeta)


class SetUserBlockedHandler:
    def __init__(
        self, users: UserRepository, sessions: SessionRepository, audit: AuditRecorder, uow: UnitOfWork, clock: Clock
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def __call__(self, cmd: SetUserBlocked) -> None:
        user = await load_user(self._users, cmd.user_id)
        if cmd.blocked == (not user.is_active):
            return
        if cmd.blocked:
            if user.id == cmd.actor.user_id:
                raise DomainError("Нельзя заблокировать собственную учётную запись", code="self_block")
            await ensure_admin_remains(self._users, user)
        try:
            if cmd.blocked:
                user.block()
                await self._sessions.revoke_all_for_user(user.id, self._clock.now())
            else:
                user.unblock()
            await self._users.save(user)
            reason = f": {cmd.reason.strip()}" if cmd.reason.strip() else ""
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.USER_BLOCKED if cmd.blocked else AuditEvent.USER_UNBLOCKED,
                    actor=cmd.actor,
                    description=f"{user.login}{reason}",
                    object_type="user",
                    object_id=str(user.id),
                    meta=cmd.meta,
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
