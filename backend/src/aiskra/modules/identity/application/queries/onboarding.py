"""Запрос: прогресс обучения интерфейсу текущего пользователя (п. 5.3)."""

from __future__ import annotations

from dataclasses import dataclass

from aiskra.modules.identity.application.ports.reader import OnboardingReader
from aiskra.modules.identity.domain.onboarding import Onboarding
from aiskra.shared.application import Query
from aiskra.shared.security import Permission, Principal


@dataclass(frozen=True, kw_only=True)
class GetOnboarding(Query):
    actor: Principal


@dataclass(frozen=True, kw_only=True)
class OnboardingView:
    enabled: bool  # показывать подсказки автоматически: только обучающимся
    dismissed: bool
    seen: list[str]


class GetOnboardingHandler:
    def __init__(self, reader: OnboardingReader) -> None:
        self._reader = reader

    async def __call__(self, query: GetOnboarding) -> OnboardingView:
        state = Onboarding.from_json(await self._reader.onboarding(query.actor.user_id))
        return OnboardingView(
            enabled=query.actor.can(Permission.TRAINING_PARTICIPATE), dismissed=state.dismissed, seen=state.seen
        )
