"""Запрос: список пользователей для администратора (поиск по логину и ФИО, фильтры роли и статуса)."""

from __future__ import annotations

from dataclasses import dataclass

from aiskra.modules.identity.application.ports.reader import UserFilter, UserListItem, UserReader
from aiskra.shared.application import Query

PAGE_MAX = 200


@dataclass(frozen=True, kw_only=True)
class ListUsers(Query):
    q: str = ""
    role: str | None = None
    status: str | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, kw_only=True)
class UserPage:
    items: list[UserListItem]
    total: int


class ListUsersHandler:
    def __init__(self, reader: UserReader) -> None:
        self._reader = reader

    async def __call__(self, query: ListUsers) -> UserPage:
        flt = UserFilter(
            q=query.q.strip(),
            role=query.role,
            status=query.status,
            limit=max(1, min(query.limit, PAGE_MAX)),
            offset=max(0, query.offset),
        )
        items, total = await self._reader.list(flt)
        return UserPage(items=items, total=total)
