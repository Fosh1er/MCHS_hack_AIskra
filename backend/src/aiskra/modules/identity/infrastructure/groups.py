"""SQL-хранилище групп: `groups` + `group_members` (таблицы из 0.2)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.identity.application.ports.groups import GroupMember, GroupView
from aiskra.modules.identity.infrastructure.models import GroupMemberModel, GroupModel, UserModel

# роль участника группы хранится в member_role: 112 | dds (в 0.2 — student | teacher, для групп обучающихся)


class SqlGroupStore:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def _members(self, group_ids: list[UUID]) -> dict[UUID, list[GroupMember]]:
        if not group_ids:
            return {}
        rows = await self._s.execute(
            select(GroupMemberModel, UserModel.full_name, UserModel.login)
            .join(UserModel, UserModel.id == GroupMemberModel.user_id)
            .where(GroupMemberModel.group_id.in_(group_ids))
            .order_by(UserModel.full_name)
        )
        out: dict[UUID, list[GroupMember]] = {}
        for m, name, login in rows.all():
            role = m.member_role if m.member_role in ("112", "dds") else "112"
            out.setdefault(m.group_id, []).append(
                GroupMember(
                    user_id=m.user_id,
                    member_role=role,
                    dds_service_code=m.dds_service_code,
                    full_name=name,
                    login=login,
                )
            )
        return out

    async def all(self) -> list[GroupView]:
        groups = (await self._s.execute(select(GroupModel).order_by(GroupModel.name))).scalars().all()
        members = await self._members([g.id for g in groups])
        return [GroupView(id=g.id, name=g.name, members=members.get(g.id, [])) for g in groups]

    async def get(self, group_id: UUID) -> GroupView | None:
        g = await self._s.get(GroupModel, group_id)
        if g is None:
            return None
        return GroupView(id=g.id, name=g.name, members=(await self._members([g.id])).get(g.id, []))

    async def name_taken(self, name: str, except_id: UUID | None = None) -> bool:
        # сравнение без учёта регистра — в Python: SQLite не приводит кириллицу к нижнему регистру
        rows = (await self._s.execute(select(GroupModel.id, GroupModel.name))).all()
        return any(n.casefold() == name.casefold() and gid != except_id for gid, n in rows)

    async def create(self, name: str) -> UUID:
        g = GroupModel(name=name)
        self._s.add(g)
        await self._s.flush()
        return g.id

    async def rename(self, group_id: UUID, name: str) -> None:
        g = await self._s.get(GroupModel, group_id)
        if g is not None:
            g.name = name
            await self._s.flush()

    async def delete(self, group_id: UUID) -> None:
        await self._s.execute(delete(GroupMemberModel).where(GroupMemberModel.group_id == group_id))
        await self._s.execute(delete(GroupModel).where(GroupModel.id == group_id))
        await self._s.flush()

    async def set_members(self, group_id: UUID, members: list[GroupMember]) -> None:
        await self._s.execute(delete(GroupMemberModel).where(GroupMemberModel.group_id == group_id))
        for m in members:
            self._s.add(
                GroupMemberModel(
                    group_id=group_id,
                    user_id=m.user_id,
                    member_role=m.member_role,
                    dds_service_code=m.dds_service_code if m.member_role == "dds" else None,
                )
            )
        await self._s.flush()

    async def active_students(self, ids: list[UUID]) -> set[UUID]:
        if not ids:
            return set()
        rows = await self._s.execute(
            select(UserModel.id).where(UserModel.id.in_(ids), UserModel.role == "student", UserModel.status == "active")
        )
        return set(rows.scalars().all())
