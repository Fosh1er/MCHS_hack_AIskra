"""Сессия входа (п. 0.3, ADR-0010). Хранится на сервере; клиенту уходит только секретный токен в cookie."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from aiskra.shared.domain import Entity


@dataclass(eq=False, kw_only=True)
class AuthSession(Entity):
    user_id: UUID
    token_hash: str  # SHA-256 токена: утечка таблицы не даёт войти
    created_at: datetime
    expires_at: datetime  # автовыход через 24 ч, как в АРМ-112
    arm_number: str | None = None
    ip: str | None = None
    user_agent: str | None = None
    revoked_at: datetime | None = None

    def is_active(self, now: datetime) -> bool:
        return self.revoked_at is None and now < self.expires_at

    def revoke(self, now: datetime) -> None:
        if self.revoked_at is None:
            self.revoked_at = now
