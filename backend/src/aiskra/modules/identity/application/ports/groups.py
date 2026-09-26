"""Порт групп обучающихся (п. 5.2): группа — именованный список участников с ролью и профилем ДДС."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class GroupMember:
    user_id: UUID
    member_role: str = "112"  # роль на занятиях по умолчанию: 112 | dds
    dds_service_code: str | None = None
    full_name: str = ""
    login: str = ""


@dataclass(frozen=True)
class GroupView:
    id: UUID
    name: str
    members: list[GroupMember] = field(default_factory=list)


class GroupStore(Protocol):
    async def all(self) -> list[GroupView]: ...

    async def get(self, group_id: UUID) -> GroupView | None: ...

    async def name_taken(self, name: str, except_id: UUID | None = None) -> bool: ...

    async def create(self, name: str) -> UUID: ...

    async def rename(self, group_id: UUID, name: str) -> None: ...

    async def delete(self, group_id: UUID) -> None: ...

    async def set_members(self, group_id: UUID, members: list[GroupMember]) -> None: ...

    async def active_students(self, ids: list[UUID]) -> set[UUID]: ...
