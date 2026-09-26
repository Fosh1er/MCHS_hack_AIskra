"""Матрица прав (ADR-0010) против ограничений ТЗ «Роли» (docs/brief/01 разд. 2)."""

from uuid import uuid4

import pytest

from aiskra.shared.errors import PermissionDeniedError
from aiskra.shared.security import ROLE_PERMISSIONS, Permission, Principal, Role


def principal(role: Role) -> Principal:
    return Principal(user_id=uuid4(), session_id=uuid4(), login="u", full_name="U", role=role)


def test_every_role_has_permissions_and_every_permission_is_granted() -> None:
    assert set(ROLE_PERMISSIONS) == set(Role)
    granted = set().union(*ROLE_PERMISSIONS.values())
    assert granted == set(Permission)


def test_admin_cannot_touch_scenarios_or_grades() -> None:
    """ТЗ 2.3: администратор не меняет оценки и сценарии."""
    admin = ROLE_PERMISSIONS[Role.ADMIN]
    assert Permission.SCENARIOS_MANAGE not in admin
    assert Permission.RESULTS_OVERRIDE not in admin
    assert {Permission.USERS_MANAGE, Permission.AUDIT_READ} <= admin


def test_teacher_has_no_admin_functions() -> None:
    """ТЗ 2.5: у преподавателя нет админ-функций."""
    teacher = ROLE_PERMISSIONS[Role.TEACHER]
    assert not teacher & {Permission.USERS_MANAGE, Permission.AUDIT_READ, Permission.SYSTEM_MANAGE}


def test_student_sees_only_own_results() -> None:
    """ТЗ 2.7: обучающийся не видит чужих результатов и не меняет сценарии."""
    student = ROLE_PERMISSIONS[Role.STUDENT]
    assert student == {Permission.DICTIONARIES_READ, Permission.TRAINING_PARTICIPATE, Permission.RESULTS_READ_OWN}


def test_ensure_raises_permission_denied() -> None:
    principal(Role.ADMIN).ensure(Permission.AUDIT_READ)
    with pytest.raises(PermissionDeniedError):
        principal(Role.STUDENT).ensure(Permission.AUDIT_READ)
