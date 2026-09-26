"""Общие правила команд управления пользователями."""

from __future__ import annotations

from uuid import UUID

from aiskra.modules.identity.application.ports.auth import UserRepository
from aiskra.modules.identity.domain.user import User
from aiskra.shared.errors import DomainError, NotFoundError


async def load_user(users: UserRepository, user_id: UUID) -> User:
    user = await users.get(user_id)
    if user is None:
        raise NotFoundError("Пользователь не найден", code="user_not_found")
    return user


async def ensure_admin_remains(users: UserRepository, target: User) -> None:
    """Нельзя оставить систему без активного администратора: его учётку некому было бы восстановить."""
    if target.is_admin and target.is_active and await users.count_active_admins() <= 1:
        raise DomainError("Это последний активный администратор", code="last_admin")
