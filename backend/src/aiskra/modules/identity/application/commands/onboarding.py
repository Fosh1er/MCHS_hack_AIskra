"""Команда: отметить экран обучения пройденным, отказаться от подсказок или начать обучение заново (п. 5.3).

Меняет только свою учётную запись. В журнал аудита не пишется: это настройка интерфейса, а не действие с данными.
"""

from __future__ import annotations

from dataclasses import dataclass

from aiskra.modules.identity.application.commands._common import load_user
from aiskra.modules.identity.application.ports.auth import UserRepository
from aiskra.modules.identity.domain.onboarding import OnboardingAction
from aiskra.shared.application import Command, UnitOfWork
from aiskra.shared.security import Principal


@dataclass(frozen=True, kw_only=True)
class UpdateOnboarding(Command):
    actor: Principal
    action: OnboardingAction
    tour: str | None = None


class UpdateOnboardingHandler:
    def __init__(self, users: UserRepository, uow: UnitOfWork) -> None:
        self._users = users
        self._uow = uow

    async def __call__(self, cmd: UpdateOnboarding) -> None:
        user = await load_user(self._users, cmd.actor.user_id)
        user.onboarding.apply(cmd.action, cmd.tour)
        try:
            await self._users.save(user)
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
