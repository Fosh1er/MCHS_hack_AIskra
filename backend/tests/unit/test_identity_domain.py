from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from aiskra.modules.identity.domain.session import AuthSession
from aiskra.modules.identity.domain.user import (
    LockoutPolicy,
    User,
    UserStatus,
    normalize_login,
    normalize_number,
    validate_password,
)
from aiskra.shared.errors import AuthenticationError, DomainError
from aiskra.shared.security import Role

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def user() -> User:
    return User.create(login=" IvanovAB ", full_name="  Иванов  Андрей ", role=Role.STUDENT, password_hash="h")


def test_login_is_case_insensitive_and_validated() -> None:
    assert normalize_login(" IvanovAB ") == "ivanovab"
    for bad in ["ab", "иванов", "-abc", "a b c"]:
        with pytest.raises(DomainError):
            normalize_login(bad)


def test_numbers_and_password_policy() -> None:
    assert normalize_number(" 123 ", what="АРМ") == "123"
    assert normalize_number("", what="АРМ") is None
    with pytest.raises(DomainError):
        normalize_number("12a", what="АРМ")
    validate_password("Secret-2026", login="ivanov")
    for password, login in [("short", "ivanov"), ("x" * 129, "ivanov"), ("Ivanov12", "ivanov12")]:
        with pytest.raises(DomainError):
            validate_password(password, login=login)


def test_create_normalizes_fields() -> None:
    u = user()
    assert (u.login, u.full_name, u.status) == ("ivanovab", "Иванов Андрей", UserStatus.ACTIVE)


def test_lockout_after_max_attempts_and_reset_on_success() -> None:
    u, policy = user(), LockoutPolicy(max_attempts=3, lock_for=timedelta(minutes=15))
    assert not u.register_failed_login(NOW, policy)
    assert not u.register_failed_login(NOW, policy)
    assert u.register_failed_login(NOW, policy)
    with pytest.raises(AuthenticationError) as exc:
        u.ensure_can_login(NOW + timedelta(minutes=1))
    assert exc.value.code == "account_locked" and "14 мин" in exc.value.message
    u.ensure_can_login(NOW + timedelta(minutes=15))
    u.register_login(NOW)
    assert u.failed_attempts == 0 and u.locked_until is None and u.last_login_at == NOW


def test_blocked_user_cannot_login_and_unblock_clears_lock() -> None:
    u = user()
    u.locked_until = NOW + timedelta(hours=1)
    u.block()
    with pytest.raises(AuthenticationError) as exc:
        u.ensure_can_login(NOW)
    assert exc.value.code == "account_blocked"
    u.unblock()
    u.ensure_can_login(NOW)


def test_update_profile_reports_changes() -> None:
    u = user()
    assert u.update_profile(full_name="Иванов Андрей") == []
    assert u.update_profile(role=Role.TEACHER, operator_number="42") == ["роль", "номер оператора"]
    assert u.update_profile(operator_number="") == ["номер оператора"] and u.operator_number is None


def test_session_expiry_and_revoke() -> None:
    s = AuthSession(user_id=uuid4(), token_hash="x", created_at=NOW, expires_at=NOW + timedelta(hours=24))
    assert s.is_active(NOW + timedelta(hours=23))
    assert not s.is_active(NOW + timedelta(hours=24))
    s.revoke(NOW)
    assert not s.is_active(NOW)
