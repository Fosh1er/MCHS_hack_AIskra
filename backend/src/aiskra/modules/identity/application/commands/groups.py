"""Команды групп обучающихся (п. 5.2). Состав группы — обучающиеся с ролью на занятиях (112 или ДДС с профилем
службы), чтобы преподаватель назначал занятие группой, а не по одному (долг 4.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from aiskra.modules.identity.application.ports.groups import GroupMember, GroupStore, GroupView
from aiskra.shared.application import Command, Query, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import DomainError, NotFoundError
from aiskra.shared.security import Principal


@dataclass(frozen=True, kw_only=True)
class SaveGroup(Command):
    """Создать (group_id = None) или изменить группу: название и состав целиком."""

    actor: Principal
    group_id: UUID | None = None
    name: str
    members: list[GroupMember] = field(default_factory=list)
    meta: RequestMeta = field(default_factory=RequestMeta)


@dataclass(frozen=True, kw_only=True)
class DeleteGroup(Command):
    actor: Principal
    group_id: UUID
    meta: RequestMeta = field(default_factory=RequestMeta)


@dataclass(frozen=True, kw_only=True)
class ListGroups(Query):
    pass


def _validate(cmd: SaveGroup) -> str:
    name = " ".join(cmd.name.split())
    if not 2 <= len(name) <= 128:
        raise DomainError("Название группы — от 2 до 128 символов", code="bad_group_name")
    ids = [m.user_id for m in cmd.members]
    if len(ids) != len(set(ids)):
        raise DomainError("Обучающийся указан в группе дважды", code="duplicate_member")
    for m in cmd.members:
        if m.member_role not in ("112", "dds"):
            raise DomainError("Роль участника — 112 или dds", code="bad_role")
        if m.member_role == "dds" and not m.dds_service_code:
            raise DomainError("Для роли ДДС укажите службу", code="service_required")
    return name


class SaveGroupHandler:
    def __init__(self, store: GroupStore, audit: AuditRecorder, uow: UnitOfWork) -> None:
        self._store = store
        self._audit = audit
        self._uow = uow

    async def __call__(self, cmd: SaveGroup) -> UUID:
        name = _validate(cmd)
        if await self._store.name_taken(name, cmd.group_id):
            raise DomainError("Группа с таким названием уже есть", code="group_exists")
        students = await self._store.active_students([m.user_id for m in cmd.members])
        if missing := [m for m in cmd.members if m.user_id not in students]:
            raise DomainError(f"Не обучающиеся или заблокированы: {len(missing)}", code="not_students")
        try:
            if cmd.group_id is None:
                gid = await self._store.create(name)
                event = AuditEvent.GROUP_CREATED
            else:
                if await self._store.get(cmd.group_id) is None:
                    raise NotFoundError("Группа не найдена", code="group_not_found")
                gid = cmd.group_id
                await self._store.rename(gid, name)
                event = AuditEvent.GROUP_UPDATED
            await self._store.set_members(gid, cmd.members)
            await self._audit.record(
                AuditEntry(
                    event=event,
                    actor=cmd.actor,
                    description=f"{name}: участников {len(cmd.members)}",
                    object_type="group",
                    object_id=str(gid),
                    meta=cmd.meta,
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return gid


class DeleteGroupHandler:
    def __init__(self, store: GroupStore, audit: AuditRecorder, uow: UnitOfWork) -> None:
        self._store = store
        self._audit = audit
        self._uow = uow

    async def __call__(self, cmd: DeleteGroup) -> None:
        g = await self._store.get(cmd.group_id)
        if g is None:
            raise NotFoundError("Группа не найдена", code="group_not_found")
        try:
            await self._store.delete(cmd.group_id)
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.GROUP_DELETED,
                    actor=cmd.actor,
                    description=g.name,
                    object_type="group",
                    object_id=str(g.id),
                    meta=cmd.meta,
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise


class ListGroupsHandler:
    def __init__(self, store: GroupStore) -> None:
        self._store = store

    async def __call__(self, q: ListGroups) -> list[GroupView]:
        return await self._store.all()
