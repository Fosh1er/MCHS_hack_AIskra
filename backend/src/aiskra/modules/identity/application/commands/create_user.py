"""Команда: создать учётную запись (администратор; CLI `create-user` — от имени системы)."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from aiskra.modules.identity.application.ports.auth import PasswordHasher, UserRepository
from aiskra.modules.identity.domain.user import User, normalize_login, validate_password
from aiskra.shared.application import Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import DomainError
from aiskra.shared.security import Principal, Role


@dataclass(frozen=True, kw_only=True)
class CreateUser(Command):
    actor: Principal | None  # None — система (CLI, начальная настройка)
    login: str
    full_name: str
    role: Role
    password: str = field(repr=False)
    operator_number: str | None = None
    meta: RequestMeta = field(default_factory=RequestMeta)


@dataclass(frozen=True, kw_only=True)
class UserCreated:
    id: UUID
    login: str


class CreateUserHandler:
    def __init__(self, users: UserRepository, hasher: PasswordHasher, audit: AuditRecorder, uow: UnitOfWork) -> None:
        self._users = users
        self._hasher = hasher
        self._audit = audit
        self._uow = uow

    async def __call__(self, cmd: CreateUser) -> UserCreated:
        login = normalize_login(cmd.login)
        validate_password(cmd.password, login=login)
        if await self._users.get_by_login(login) is not None:
            raise DomainError(f"Логин «{login}» уже занят", code="login_taken")
        user = User.create(
            login=login,
            full_name=cmd.full_name,
            role=cmd.role,
            password_hash=await self._hasher.hash(cmd.password),
            operator_number=cmd.operator_number,
        )
        try:
            await self._users.add(user)
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.USER_CREATED,
                    actor=cmd.actor,
                    description=f"{user.login} — {user.full_name} ({user.role.label})",
                    object_type="user",
                    object_id=str(user.id),
                    meta=cmd.meta,
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return UserCreated(id=user.id, login=user.login)
