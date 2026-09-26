"""Команда: выход из системы — отзыв текущей сессии."""

from __future__ import annotations

from dataclasses import dataclass, field

from aiskra.modules.identity.application.ports.auth import SessionRepository
from aiskra.shared.application import Clock, Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.security import Principal


@dataclass(frozen=True, kw_only=True)
class Logout(Command):
    actor: Principal
    meta: RequestMeta = field(default_factory=RequestMeta)


class LogoutHandler:
    def __init__(self, sessions: SessionRepository, audit: AuditRecorder, uow: UnitOfWork, clock: Clock) -> None:
        self._sessions = sessions
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def __call__(self, cmd: Logout) -> None:
        session = await self._sessions.get(cmd.actor.session_id)
        if session is None:
            return
        try:
            session.revoke(self._clock.now())
            await self._sessions.save(session)
            await self._audit.record(AuditEntry(event=AuditEvent.LOGOUT, actor=cmd.actor, meta=cmd.meta))
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
