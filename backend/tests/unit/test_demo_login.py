"""F2 без БД: демо-вход и список демо-учёток на фейках портов, режимы окружения, лимит частоты."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

import pytest
from pydantic import SecretStr, ValidationError

from aiskra.bootstrap import build_demo_policy
from aiskra.modules.identity.application.commands.demo_login import DemoLogin, DemoLoginHandler
from aiskra.modules.identity.application.commands.login import LoginHandler
from aiskra.modules.identity.application.ports.auth import AuthPolicy
from aiskra.modules.identity.application.ports.demo import DemoAccountSpec, DemoPolicy
from aiskra.modules.identity.application.ports.reader import UserListItem
from aiskra.modules.identity.application.queries.demo_accounts import ListDemoAccounts, ListDemoAccountsHandler
from aiskra.modules.identity.domain.user import User
from aiskra.platform.ratelimit import SlidingWindowThrottle
from aiskra.platform.settings import Settings
from aiskra.shared.audit import RequestMeta
from aiskra.shared.errors import AuthenticationError, NotFoundError, TooManyRequestsError
from aiskra.shared.security import Role
from tests.unit.identity_fakes import (
    CountingTokens,
    FakeAudit,
    FakeSessions,
    FakeUow,
    FakeUsers,
    FixedClock,
    PlainHasher,
)

POLICY = DemoPolicy(
    enabled=True,
    accounts=(
        DemoAccountSpec(login="op1", title="Оператор 112", hint=("Журнал 112",), arm_number="101"),
        DemoAccountSpec(login="boss", title="Администратор", arm_number="1"),  # ошибка конфигурации
        DemoAccountSpec(login="op2", title="Оператор 112", arm_number="102"),
    ),
)


def user(login: str, role: Role = Role.STUDENT) -> User:
    return User.create(login=login, full_name=f"Пользователь {login}", role=role, password_hash="plain:Secret-2026")


class World:
    def __init__(self, *users: User, demo: DemoPolicy = POLICY) -> None:
        self.users = FakeUsers(*users)
        self.sessions = FakeSessions()
        self.audit = FakeAudit()
        self.uow = FakeUow()
        self.clock = FixedClock()
        self.demo = demo

    def handler(self) -> DemoLoginHandler:
        login = LoginHandler(
            self.users,
            self.sessions,
            PlainHasher(),
            CountingTokens(),
            self.audit,
            self.uow,
            self.clock,
            AuthPolicy(session_ttl=timedelta(hours=24)),
        )
        return DemoLoginHandler(login, self.users, self.audit, self.uow, self.clock, self.demo)


async def test_demo_login_opens_session_with_default_arm() -> None:
    w = World(user("op1"))
    result = await w.handler()(DemoLogin(login=" OP1 ", meta=RequestMeta(ip="10.0.0.9")))
    assert result.principal.login == "op1" and result.principal.arm_number == "101"
    assert w.audit.events == ["auth.demo_login"] and w.audit.entries[0].meta.ip == "10.0.0.9"
    assert w.uow.commits == 1 and len(w.sessions.by_id) == 1


@pytest.mark.parametrize("login", ["boss", "op2", "ghost", "student"])
async def test_only_existing_non_admin_demo_accounts(login: str) -> None:
    w = World(user("op1"), user("boss", Role.ADMIN), user("student"))
    with pytest.raises(NotFoundError):
        await w.handler()(DemoLogin(login=login))
    assert not w.sessions.by_id and not w.audit.events


async def test_disabled_policy_refuses_everyone() -> None:
    w = World(user("op1"), demo=DemoPolicy(enabled=False, accounts=POLICY.accounts))
    with pytest.raises(NotFoundError):
        await w.handler()(DemoLogin(login="op1"))


async def test_blocked_account_refused_and_audited() -> None:
    u = user("op1")
    u.block()
    w = World(u)
    with pytest.raises(AuthenticationError) as exc:
        await w.handler()(DemoLogin(login="op1"))
    assert exc.value.code == "account_blocked" and w.audit.events == ["auth.login_failed"] and w.uow.commits == 1


class Reader:
    def __init__(self, *users: User) -> None:
        self.users = users

    async def list(self, flt: object) -> tuple[list[UserListItem], int]:
        raise NotImplementedError

    async def by_logins(self, logins: Sequence[str]) -> Sequence[UserListItem]:
        return [
            UserListItem(
                id=u.id,
                login=u.login,
                full_name=u.full_name,
                role=u.role.value,
                status=u.status.value,
                operator_number=u.operator_number,
                locked_until=None,
                last_login_at=None,
                created_at=FixedClock().now(),
            )
            for u in self.users
            if u.login in logins
        ]


async def test_list_shows_existing_active_non_admin_without_password() -> None:
    blocked = user("op2")
    blocked.block()
    result = await ListDemoAccountsHandler(Reader(user("op1"), user("boss", Role.ADMIN), blocked), POLICY)(
        ListDemoAccounts()
    )
    assert [a.login for a in result.accounts] == ["op1"] and result.password is None
    assert result.accounts[0].full_name == "Пользователь op1" and result.accounts[0].hint == ("Журнал 112",)


async def test_list_disabled_is_not_found() -> None:
    with pytest.raises(NotFoundError):
        await ListDemoAccountsHandler(Reader(user("op1")), DemoPolicy())(ListDemoAccounts())


def test_app_env_values() -> None:
    assert Settings(app_env=" PROD ").app_env == "prod" and not Settings(app_env="prod").demo_enabled
    assert Settings(app_env="demo").demo_enabled and Settings(app_env="dev").demo_enabled
    with pytest.raises(ValidationError):
        Settings(app_env="staging")


def test_demo_policy_from_settings() -> None:
    secret = SecretStr("Demo-Stand-2026")
    on = build_demo_policy(Settings(app_env="demo", demo_password=secret, demo_show_password=True))
    assert on.enabled and on.password == "Demo-Stand-2026" and "Demo-Stand-2026" not in repr(on)
    assert [a.login for a in on.accounts] == ["teacher", "op1", "op2", "dds1", "dds2"]
    off = Settings(app_env="demo", demo_password=secret, demo_show_password=False)
    assert build_demo_policy(off).password is None  # показ выключен явно
    prod = build_demo_policy(Settings(app_env="prod", demo_password=secret))  # рекомендации экспертов: и в prod
    assert prod.enabled and prod.password == "Demo-Stand-2026"
    closed = build_demo_policy(Settings(app_env="prod", demo_password=secret, demo_in_prod=False))
    assert not closed.enabled and closed.password is None and closed.find("op1") is None
    assert not build_demo_policy(Settings(app_env="prod")).enabled  # без пароля демо-учёток — нет


def test_hit_counts_every_request() -> None:
    now = [0.0]
    t = SlidingWindowThrottle(limit=10, window_s=60, clock=lambda: now[0], message="Слишком много демо-входов")
    for _ in range(10):
        t.check("ip")
        t.hit("ip")
    with pytest.raises(TooManyRequestsError) as exc:
        t.check("ip")
    assert exc.value.message.startswith("Слишком много демо-входов")
    now[0] = 61
    t.check("ip")
