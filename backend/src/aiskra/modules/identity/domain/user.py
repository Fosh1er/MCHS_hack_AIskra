"""Пользователь и правила входа (п. 0.3). Чистый домен: хеширование пароля — порт в application."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

from aiskra.shared.domain import Entity
from aiskra.shared.errors import AuthenticationError, DomainError
from aiskra.shared.security import Role

_LOGIN = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,63}$")
_DIGITS = re.compile(r"^\d{1,6}$")
FULL_NAME_MAX = 255
PASSWORD_MIN = 8
PASSWORD_MAX = 128


class UserStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"  # заблокирован администратором (бессрочно)


def normalize_login(raw: str) -> str:
    """Логин без учёта регистра: «IvanovAB» и «ivanovab» — один пользователь."""
    login = raw.strip().lower()
    if not _LOGIN.match(login):
        raise DomainError(
            "Логин: 3–64 символа — латинские буквы, цифры, «_», «.», «-»; начинается с буквы или цифры",
            code="bad_login",
        )
    return login


def normalize_number(raw: str | None, *, what: str) -> str | None:
    """Номер АРМ или оператора: 1–6 цифр, пустое значение — None."""
    value = (raw or "").strip()
    if not value:
        return None
    if not _DIGITS.match(value):
        raise DomainError(f"{what}: от 1 до 6 цифр", code="bad_number")
    return value


def validate_password(password: str, *, login: str) -> None:
    if not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        raise DomainError(f"Пароль: от {PASSWORD_MIN} до {PASSWORD_MAX} символов", code="weak_password")
    if password.strip().lower() == login:
        raise DomainError("Пароль не должен совпадать с логином", code="weak_password")


def _full_name(raw: str) -> str:
    name = " ".join(raw.split())
    if not name or len(name) > FULL_NAME_MAX:
        raise DomainError(f"ФИО: от 1 до {FULL_NAME_MAX} символов", code="bad_full_name")
    return name


@dataclass(frozen=True, kw_only=True)
class LockoutPolicy:
    """Защита от подбора пароля: после `max_attempts` неудач подряд вход закрыт на `lock_for`."""

    max_attempts: int = 5
    lock_for: timedelta = timedelta(minutes=15)


@dataclass(eq=False, kw_only=True)
class User(Entity):
    login: str
    full_name: str
    role: Role
    password_hash: str = field(repr=False)
    status: UserStatus = UserStatus.ACTIVE
    operator_number: str | None = None
    failed_attempts: int = 0
    locked_until: datetime | None = None
    last_login_at: datetime | None = None

    @classmethod
    def create(
        cls, *, login: str, full_name: str, role: Role, password_hash: str, operator_number: str | None = None
    ) -> User:
        return cls(
            login=normalize_login(login),
            full_name=_full_name(full_name),
            role=role,
            password_hash=password_hash,
            operator_number=normalize_number(operator_number, what="Номер оператора"),
        )

    @property
    def is_admin(self) -> bool:
        return self.role is Role.ADMIN

    @property
    def is_active(self) -> bool:
        return self.status is UserStatus.ACTIVE

    def is_locked(self, now: datetime) -> bool:
        return self.locked_until is not None and now < self.locked_until

    def ensure_can_login(self, now: datetime) -> None:
        """Проверки до сверки пароля. Пароль при блокировке не проверяется — перебор бесполезен."""
        if not self.is_active:
            raise AuthenticationError(
                "Учётная запись заблокирована. Обратитесь к администратору", code="account_blocked"
            )
        if self.locked_until is not None and now < self.locked_until:
            minutes = math.ceil((self.locked_until - now).total_seconds() / 60)
            raise AuthenticationError(
                f"Слишком много неудачных попыток входа. Повторите через {minutes} мин.", code="account_locked"
            )

    def register_failed_login(self, now: datetime, policy: LockoutPolicy) -> bool:
        """Учесть неверный пароль. Возвращает True, если именно эта попытка закрыла вход."""
        self.failed_attempts += 1
        if self.failed_attempts >= policy.max_attempts:
            self.failed_attempts = 0
            self.locked_until = now + policy.lock_for
            return True
        return False

    def register_login(self, now: datetime) -> None:
        self.failed_attempts = 0
        self.locked_until = None
        self.last_login_at = now

    def update_profile(
        self, *, full_name: str | None = None, role: Role | None = None, operator_number: str | None = None
    ) -> list[str]:
        """Изменить карточку пользователя. Возвращает названия изменённых полей (для аудита)."""
        changed: list[str] = []
        if full_name is not None and (name := _full_name(full_name)) != self.full_name:
            self.full_name = name
            changed.append("ФИО")
        if role is not None and role is not self.role:
            self.role = role
            changed.append("роль")
        if operator_number is not None:
            number = normalize_number(operator_number, what="Номер оператора")
            if number != self.operator_number:
                self.operator_number = number
                changed.append("номер оператора")
        return changed

    def block(self) -> None:
        self.status = UserStatus.BLOCKED

    def unblock(self) -> None:
        self.status = UserStatus.ACTIVE
        self.failed_attempts = 0
        self.locked_until = None

    def set_password_hash(self, password_hash: str) -> None:
        self.password_hash = password_hash
        self.failed_attempts = 0
        self.locked_until = None
