"""Роли, права и субъект доступа (RBAC, п. 0.3, ADR-0010). Чистый Python — общий для всех модулей.

Матрица прав повторяет ТЗ (разд. «Роли»; docs/brief/01 разд. 2):
- администратор управляет учётками, системой и аудитом, но не сценариями и оценками;
- преподаватель ведёт сценарии, занятия и оценки, но не имеет админ-функций;
- обучающийся выполняет задания и видит только свои результаты.

Модули проверяют права только через `Permission`, а не через роль: так матрица меняется в одном месте.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from aiskra.shared.errors import PermissionDeniedError


class Role(StrEnum):
    ADMIN = "admin"
    TEACHER = "teacher"
    STUDENT = "student"

    @property
    def label(self) -> str:
        return ROLE_TITLES[self]


ROLE_TITLES: Mapping[Role, str] = {
    Role.ADMIN: "Администратор",
    Role.TEACHER: "Преподаватель",
    Role.STUDENT: "Обучающийся",
}


class Permission(StrEnum):
    # администрирование
    USERS_MANAGE = "users.manage"
    AUDIT_READ = "audit.read"
    SYSTEM_MANAGE = "system.manage"
    DICTIONARIES_IMPORT = "dictionaries.import"
    # общее
    DICTIONARIES_READ = "dictionaries.read"
    # преподаватель (пункты 3.x, 4.x)
    SCENARIOS_MANAGE = "scenarios.manage"
    LESSONS_CONDUCT = "lessons.conduct"
    RESULTS_READ_ALL = "results.read_all"
    RESULTS_OVERRIDE = "results.override"
    CARDS_CHECK = "cards.check"  # «Проверена» / «Вернуть на доработку» — главный специалист (п. 1.3)
    # обучающийся (пункты 1.x, 2.x, 5.1)
    TRAINING_PARTICIPATE = "training.participate"
    RESULTS_READ_OWN = "results.read_own"


ROLE_PERMISSIONS: Mapping[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(
        {
            Permission.USERS_MANAGE,
            Permission.AUDIT_READ,
            Permission.SYSTEM_MANAGE,
            Permission.DICTIONARIES_IMPORT,
            Permission.DICTIONARIES_READ,
        }
    ),
    Role.TEACHER: frozenset(
        {
            Permission.DICTIONARIES_READ,
            Permission.SCENARIOS_MANAGE,
            Permission.LESSONS_CONDUCT,
            Permission.RESULTS_READ_ALL,
            Permission.RESULTS_OVERRIDE,
            Permission.CARDS_CHECK,
        }
    ),
    Role.STUDENT: frozenset(
        {
            Permission.DICTIONARIES_READ,
            Permission.TRAINING_PARTICIPATE,
            Permission.RESULTS_READ_OWN,
        }
    ),
}


@dataclass(frozen=True, kw_only=True)
class Principal:
    """Аутентифицированный пользователь в рамках одной сессии входа."""

    user_id: UUID
    session_id: UUID
    login: str
    full_name: str
    role: Role
    operator_number: str | None = None  # «Опер.» в карточке и аудите
    arm_number: str | None = None  # номер АРМ, введённый при входе

    @property
    def permissions(self) -> frozenset[Permission]:
        return ROLE_PERMISSIONS[self.role]

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions

    def ensure(self, permission: Permission) -> None:
        if not self.can(permission):
            raise PermissionDeniedError(
                f"Недостаточно прав: роль «{self.role.label}» не имеет права «{permission.value}»",
                code="permission_denied",
            )
