"""Команда: изменить ФИО, роль или номер оператора. Новая роль действует со следующего запроса."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from aiskra.modules.identity.application.commands._common import ensure_admin_remains, load_user
from aiskra.modules.identity.application.ports.auth import UserRepository
from aiskra.shared.application import Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.security import Principal, Role


@dataclass(frozen=True, kw_only=True)
class UpdateUser(Command):
    actor: Principal
    user_id: UUID
    full_name: str | None = None
    role: Role | None = None
    operator_number: str | None = None  # "" — очистить
    meta: RequestMeta = field(default_factory=RequestMeta)


class UpdateUserHandler:
    def __init__(self, users: UserRepository, audit: AuditRecorder, uow: UnitOfWork) -> None:
        self._users = users
        self._audit = audit
        self._uow = uow

    async def __call__(self, cmd: UpdateUser) -> list[str]:
        user = await load_user(self._users, cmd.user_id)
        if cmd.role is not None and cmd.role is not Role.ADMIN:
            await ensure_admin_remains(self._users, user)
        changed = user.update_profile(full_name=cmd.full_name, role=cmd.role, operator_number=cmd.operator_number)
        if not changed:
            return []
        try:
            await self._users.save(user)
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.USER_UPDATED,
                    actor=cmd.actor,
                    description=f"{user.login}: изменены {', '.join(changed)}",
                    object_type="user",
                    object_id=str(user.id),
                    meta=cmd.meta,
                    data={"role": user.role.value} if "роль" in changed else {},
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return changed
