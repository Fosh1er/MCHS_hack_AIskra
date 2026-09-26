"""SQL-очистка журнала аудита старше даты."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.audit.infrastructure.models import AuditLogModel


class SqlAuditPurger:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def count_older(self, before: datetime) -> int:
        return int((await self._s.execute(select(func.count()).where(AuditLogModel.at < before))).scalar_one())

    async def delete_older(self, before: datetime) -> int:
        n = await self.count_older(before)
        await self._s.execute(delete(AuditLogModel).where(AuditLogModel.at < before))
        await self._s.flush()
        return n
