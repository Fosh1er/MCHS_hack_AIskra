"""Демо-стенд (F2): какие учётки входят одной кнопкой и ограничение частоты демо-входа.

Список учёток и режим окружения приходят из composition root (`DEMO_USERS` в `demo_seed.py`,
`AISKRA_APP_ENV`), модуль identity о них ничего не знает.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, kw_only=True)
class DemoAccountSpec:
    """Демо-учётка на странице входа: подпись роли, «что посмотреть», номер АРМ при демо-входе."""

    login: str
    title: str
    hint: tuple[str, ...] = ()
    arm_number: str | None = None


@dataclass(frozen=True, kw_only=True)
class DemoPolicy:
    """`enabled` — режим demo или dev. `password` задаётся, только если показ пароля включён явно
    (`AISKRA_DEMO_SHOW_PASSWORD=true`); иначе пароль в API не попадает."""

    enabled: bool = False
    accounts: tuple[DemoAccountSpec, ...] = ()
    password: str | None = field(default=None, repr=False)

    def find(self, login: str) -> DemoAccountSpec | None:
        if not self.enabled:
            return None
        return next((a for a in self.accounts if a.login == login), None)


class RequestLimit(Protocol):
    """Ограничение частоты запросов с одного адреса: считается каждый запрос, не только неудачный."""

    def check(self, key: str) -> None:
        """Бросает TooManyRequestsError, если лимит исчерпан."""
        ...

    def hit(self, key: str) -> None: ...
