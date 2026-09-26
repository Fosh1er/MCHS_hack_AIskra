"""Команды identity с фейками портов: вход, защита от подбора, управление пользователями."""

from datetime import timedelta
from uuid import uuid4

import pytest

from aiskra.modules.identity.application.commands.create_user import CreateUser, CreateUserHandler
from aiskra.modules.identity.application.commands.login import Login, LoginHandler
from aiskra.modules.identity.application.commands.logout import Logout, LogoutHandler
from aiskra.modules.identity.application.commands.reset_password import ResetPassword, ResetPasswordHandler
from aiskra.modules.identity.application.commands.set_user_blocked import SetUserBlocked, SetUserBlockedHandler
from aiskra.modules.identity.application.commands.update_user import UpdateUser, UpdateUserHandler
from aiskra.modules.identity.application.ports.auth import AuthPolicy
from aiskra.modules.identity.application.ports.reader import SessionView
from aiskra.modules.identity.application.queries.resolve_session import ResolveSession, ResolveSessionHandler
from aiskra.modules.identity.domain.user import LockoutPolicy, User, UserStatus
from aiskra.shared.audit import RequestMeta
from aiskra.shared.errors import AuthenticationError, DomainError
from aiskra.shared.security import Principal, Role
from tests.unit.identity_fakes import (
    CountingTokens,
    FakeAudit,
    FakeSessions,
    FakeUow,
    FakeUsers,
    FixedClock,
    PlainHasher,
)

POLICY = AuthPolicy(session_ttl=timedelta(hours=24), lockout=LockoutPolicy(max_attempts=3))


class SessionReaderOverFakes:
    """SessionReader поверх фейковых хранилищ — чтобы проверить путь «вход → запрос с токеном»."""

    def __init__(self, users: FakeUsers, sessions: FakeSessions) -> None:
        self.users, self.sessions = users, sessions

    async def find_by_token_hash(self, token_hash: str) -> SessionView | None:
        s = next((s for s in self.sessions.by_id.values() if s.token_hash == token_hash), None)
        if s is None:
            return None
        u = self.users.by_id[s.user_id]
        return SessionView(
            session_id=s.id,
            expires_at=s.expires_at,
            revoked_at=s.revoked_at,
            arm_number=s.arm_number,
            user_id=u.id,
            login=u.login,
            full_name=u.full_name,
            role=u.role.value,
            user_status=u.status.value,
            operator_number=u.operator_number,
        )


class World:
    def __init__(self, *users: User) -> None:
        self.users = FakeUsers(*users)
        self.sessions = FakeSessions()
        self.hasher = PlainHasher()
        self.tokens = CountingTokens()
        self.audit = FakeAudit()
        self.uow = FakeUow()
        self.clock = FixedClock()

    def login(self) -> LoginHandler:
        return LoginHandler(
            self.users, self.sessions, self.hasher, self.tokens, self.audit, self.uow, self.clock, POLICY
        )

    def resolve(self) -> ResolveSessionHandler:
        return ResolveSessionHandler(SessionReaderOverFakes(self.users, self.sessions), self.tokens, self.clock)


def make_user(login: str = "ivanov", role: Role = Role.STUDENT, password: str = "Secret-2026") -> User:
    return User.create(login=login, full_name=f"Пользователь {login}", role=role, password_hash=f"plain:{password}")


def as_principal(u: User) -> Principal:
    return Principal(user_id=u.id, session_id=uuid4(), login=u.login, full_name=u.full_name, role=u.role)


async def test_login_opens_session_and_resolves_principal() -> None:
    w = World(make_user())
    meta = RequestMeta(ip="10.0.0.5", user_agent="pytest")
    result = await w.login()(Login(login=" IVANOV ", password="Secret-2026", arm_number="123", meta=meta))
    assert result.principal.arm_number == "123" and result.principal.role is Role.STUDENT
    assert result.expires_at == w.clock.now() + timedelta(hours=24)
    assert w.audit.events == ["auth.login_succeeded"] and w.audit.entries[0].meta.ip == "10.0.0.5"
    assert w.uow.commits == 1
    principal = await w.resolve()(ResolveSession(token=result.token))
    assert principal.user_id == result.principal.user_id and principal.arm_number == "123"


async def test_unknown_login_spends_hash_time_and_is_audited() -> None:
    w = World()
    with pytest.raises(AuthenticationError) as exc:
        await w.login()(Login(login="ghost", password="x"))
    assert exc.value.code == "unauthenticated" and exc.value.message == "Неверный логин или пароль"
    assert w.hasher.burned == 1
    assert w.audit.events == ["auth.login_failed"] and w.audit.entries[0].actor_login == "ghost"
    assert w.uow.commits == 1  # попытка сохранена, несмотря на ошибку


async def test_bruteforce_locks_account_even_for_correct_password() -> None:
    u = make_user()
    w = World(u)
    for _ in range(3):
        with pytest.raises(AuthenticationError):
            await w.login()(Login(login="ivanov", password="wrong"))
    assert "auth.account_locked" in w.audit.events and u.locked_until is not None
    with pytest.raises(AuthenticationError) as exc:
        await w.login()(Login(login="ivanov", password="Secret-2026"))
    assert exc.value.code == "account_locked"
    w.clock.advance(minutes=16)
    await w.login()(Login(login="ivanov", password="Secret-2026"))


async def test_blocked_user_and_bad_arm_number() -> None:
    u = make_user()
    u.block()
    w = World(u)
    with pytest.raises(AuthenticationError) as exc:
        await w.login()(Login(login="ivanov", password="Secret-2026"))
    assert exc.value.code == "account_blocked"
    with pytest.raises(DomainError):
        await w.login()(Login(login="ivanov", password="Secret-2026", arm_number="АРМ-1"))


async def test_logout_revokes_session_and_expired_session_is_rejected() -> None:
    w = World(make_user())
    result = await w.login()(Login(login="ivanov", password="Secret-2026"))
    await LogoutHandler(w.sessions, w.audit, w.uow, w.clock)(Logout(actor=result.principal))
    with pytest.raises(AuthenticationError):
        await w.resolve()(ResolveSession(token=result.token))

    second = await w.login()(Login(login="ivanov", password="Secret-2026"))
    w.clock.advance(hours=24)
    with pytest.raises(AuthenticationError) as exc:
        await w.resolve()(ResolveSession(token=second.token))
    assert exc.value.code == "session_expired"
    with pytest.raises(AuthenticationError):
        await w.resolve()(ResolveSession(token=None))


async def test_create_user_rejects_duplicates_and_weak_passwords() -> None:
    w = World(make_user())
    handler = CreateUserHandler(w.users, w.hasher, w.audit, w.uow)
    created = await handler(
        CreateUser(actor=None, login="Petrov", full_name="Петров П. П.", role=Role.TEACHER, password="Teacher-2026")
    )
    assert created.login == "petrov" and w.audit.events == ["users.created"]
    with pytest.raises(DomainError) as exc:
        await handler(CreateUser(actor=None, login="IVANOV", full_name="x", role=Role.STUDENT, password="Pass-2026!"))
    assert exc.value.code == "login_taken"
    with pytest.raises(DomainError):
        await handler(CreateUser(actor=None, login="sidorov", full_name="x", role=Role.STUDENT, password="short"))


async def test_block_revokes_sessions_and_protects_self_and_last_admin() -> None:
    admin, student = make_user("admin", Role.ADMIN), make_user()
    w = World(admin, student)
    await w.login()(Login(login="ivanov", password="Secret-2026"))
    block = SetUserBlockedHandler(w.users, w.sessions, w.audit, w.uow, w.clock)
    actor = as_principal(admin)

    await block(SetUserBlocked(actor=actor, user_id=student.id, blocked=True, reason="отчислен"))
    assert student.status is UserStatus.BLOCKED
    assert all(s.revoked_at is not None for s in w.sessions.by_id.values())
    assert w.audit.entries[-1].description == "ivanov: отчислен"

    with pytest.raises(DomainError) as exc:
        await block(SetUserBlocked(actor=actor, user_id=admin.id, blocked=True))
    assert exc.value.code == "self_block"

    other_admin = make_user("root", Role.ADMIN)
    await w.users.add(other_admin)
    await block(SetUserBlocked(actor=actor, user_id=other_admin.id, blocked=True))
    with pytest.raises(DomainError) as exc:
        await UpdateUserHandler(w.users, w.audit, w.uow)(UpdateUser(actor=actor, user_id=admin.id, role=Role.TEACHER))
    assert exc.value.code == "last_admin"


async def test_reset_password_revokes_sessions_and_clears_lock() -> None:
    admin, student = make_user("admin", Role.ADMIN), make_user()
    w = World(admin, student)
    old = await w.login()(Login(login="ivanov", password="Secret-2026"))
    student.locked_until = w.clock.now() + timedelta(minutes=5)
    await ResetPasswordHandler(w.users, w.sessions, w.hasher, w.audit, w.uow, w.clock)(
        ResetPassword(actor=as_principal(admin), user_id=student.id, new_password="Brand-New-2026")
    )
    assert student.locked_until is None and w.audit.events[-1] == "users.password_reset"
    with pytest.raises(AuthenticationError):
        await w.resolve()(ResolveSession(token=old.token))
    await w.login()(Login(login="ivanov", password="Brand-New-2026"))
