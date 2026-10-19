"""Запрос: демо-учётки для страницы входа (F2, только режимы demo и dev).

Показываются только учётки, которые есть в базе и не заблокированы, без администратора.
Пароль — только если его показ включён явно (`AISKRA_DEMO_SHOW_PASSWORD=true`).
"""

from __future__ import annotations

from dataclasses import dataclass

from aiskra.modules.identity.application.ports.demo import DemoPolicy
from aiskra.modules.identity.application.ports.reader import UserReader
from aiskra.modules.identity.domain.user import UserStatus
from aiskra.shared.application import Query
from aiskra.shared.errors import NotFoundError
from aiskra.shared.security import Role


@dataclass(frozen=True, kw_only=True)
class ListDemoAccounts(Query):
    pass


@dataclass(frozen=True, kw_only=True)
class DemoAccountView:
    login: str
    role: Role
    title: str
    full_name: str
    hint: tuple[str, ...]
    arm_number: str | None


@dataclass(frozen=True, kw_only=True)
class DemoAccounts:
    accounts: list[DemoAccountView]
    password: str | None  # None — пароль не показывается (по умолчанию)


class ListDemoAccountsHandler:
    def __init__(self, reader: UserReader, demo: DemoPolicy) -> None:
        self._reader = reader
        self._demo = demo

    async def __call__(self, query: ListDemoAccounts) -> DemoAccounts:
        if not self._demo.enabled:
            raise NotFoundError("Демо-вход выключен", code="demo_disabled")
        found = {
            u.login: u
            for u in await self._reader.by_logins([a.login for a in self._demo.accounts])
            if u.status == UserStatus.ACTIVE.value and u.role != Role.ADMIN.value
        }
        accounts = [
            DemoAccountView(
                login=spec.login,
                role=Role(user.role),
                title=spec.title or Role(user.role).label,
                full_name=user.full_name,
                hint=spec.hint,
                arm_number=spec.arm_number,
            )
            for spec in self._demo.accounts
            if (user := found.get(spec.login)) is not None
        ]
        return DemoAccounts(accounts=accounts, password=self._demo.password if accounts else None)
