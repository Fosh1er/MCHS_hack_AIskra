"""Реализации порта `AuditRecorder` (aiskra.shared.audit).

- `SqlAuditRecorder` пишет в сессию запроса: запись фиксируется вместе с командой или не фиксируется вовсе.
- `IsolatedAuditRecorder` пишет в отдельной короткой транзакции: для событий, которые должны остаться
  в журнале, даже если сам запрос завершится ошибкой (отказ в доступе).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aiskra.modules.audit.infrastructure.models import AuditLogModel
from aiskra.shared.audit import AuditEntry
from aiskra.shared.text import search_key


def _to_row(entry: AuditEntry) -> AuditLogModel:
    actor = entry.actor
    actor_name = actor.full_name if actor else None
    actor_login = actor.login if actor else entry.actor_login
    return AuditLogModel(
        at=datetime.now(UTC),
        card_number=entry.card_number,
        operator_number=actor.operator_number if actor else None,
        actor_id=actor.user_id if actor else None,
        actor_name=actor_name,
        actor_login=actor_login,
        actor_key=search_key(actor_name, actor_login) or None,
        description_key=search_key(entry.description) or None,
        actor_role=actor.role.value if actor else None,
        arm_number=actor.arm_number if actor else None,
        event=entry.event.value,
        description=entry.description or None,
        object_type=entry.object_type,
        object_id=entry.object_id,
        ip=entry.meta.ip,
        data=dict(entry.data),
    )


class SqlAuditRecorder:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def record(self, entry: AuditEntry) -> None:
        self._s.add(_to_row(entry))


class IsolatedAuditRecorder:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def record(self, entry: AuditEntry) -> None:
        async with self._factory() as session:
            session.add(_to_row(entry))
            await session.commit()
