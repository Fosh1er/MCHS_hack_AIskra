"""Прогресс обучения интерфейсу (п. 5.3): какие экраны пользователь уже прошёл и не отказался ли от подсказок.

Содержимое подсказок живёт на фронтенде; здесь — только идентификаторы экранов, поэтому формат строго ограничен:
поле хранится в таблице пользователей и не должно расти бесконтрольно.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from aiskra.shared.errors import DomainError

_TOUR_ID = re.compile(r"^[a-z0-9-]{1,40}$")
MAX_TOURS = 50


class OnboardingAction(StrEnum):
    SEEN = "seen"  # экран пройден до конца или закрыт
    DISMISS = "dismiss"  # «пропустить обучение»: больше не показывать ничего
    RESET = "reset"  # «пройти обучение заново»


def check_tour_id(raw: str) -> str:
    tour = raw.strip()
    if not _TOUR_ID.match(tour):
        raise DomainError("Экран обучения: 1–40 символов — латинские буквы, цифры, «-»", code="bad_tour")
    return tour


@dataclass(kw_only=True)
class Onboarding:
    dismissed: bool = False
    seen: list[str] = field(default_factory=list)

    @classmethod
    def from_json(cls, raw: Any) -> Onboarding:
        """Из поля БД; пустое или повреждённое значение — «ничего не пройдено»."""
        if not isinstance(raw, dict):
            return cls()
        seen = [s for s in raw.get("seen", []) if isinstance(s, str) and _TOUR_ID.match(s)]
        return cls(dismissed=bool(raw.get("dismissed", False)), seen=seen[:MAX_TOURS])

    def to_json(self) -> dict[str, Any]:
        return {"dismissed": self.dismissed, "seen": list(self.seen)}

    def apply(self, action: OnboardingAction, tour: str | None = None) -> None:
        if action is OnboardingAction.SEEN:
            if tour is None:
                raise DomainError("Не указан экран обучения", code="bad_tour")
            tour = check_tour_id(tour)
            if tour not in self.seen:
                if len(self.seen) >= MAX_TOURS:
                    raise DomainError(f"Экранов обучения не больше {MAX_TOURS}", code="bad_tour")
                self.seen.append(tour)
        elif action is OnboardingAction.DISMISS:
            self.dismissed = True
        else:
            self.dismissed = False
            self.seen = []
