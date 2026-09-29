"""Запрос: прогресс обучения интерфейсу текущего пользователя (п. 5.3, 5.4)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from aiskra.modules.identity.application.ports.reader import OnboardingReader
from aiskra.modules.identity.domain.onboarding import Onboarding
from aiskra.shared.application import Query
from aiskra.shared.security import Permission, Principal


@dataclass(frozen=True, kw_only=True)
class GetOnboarding(Query):
    actor: Principal


Audience = Literal["student", "teacher"]


def audience_of(actor: Principal) -> Audience | None:
    """Чьи подсказки показывать сами — по правам, а не по названию роли: обучающемуся — его экраны АРМ и кабинета,
    тому, кто ведёт занятия, — экраны преподавателя; администратору — ничего (п. 5.4, R5.4-03)."""
    if actor.can(Permission.TRAINING_PARTICIPATE):
        return "student"
    if actor.can(Permission.LESSONS_CONDUCT):
        return "teacher"
    return None


@dataclass(frozen=True, kw_only=True)
class OnboardingView:
    enabled: bool  # показывать подсказки автоматически (есть аудитория)
    audience: Audience | None
    dismissed: bool
    seen: list[str]


class GetOnboardingHandler:
    def __init__(self, reader: OnboardingReader) -> None:
        self._reader = reader

    async def __call__(self, query: GetOnboarding) -> OnboardingView:
        state = Onboarding.from_json(await self._reader.onboarding(query.actor.user_id))
        audience = audience_of(query.actor)
        return OnboardingView(
            enabled=audience is not None, audience=audience, dismissed=state.dismissed, seen=state.seen
        )
