"""Порты хранения журнала аудита (п. 6.2): срок хранения и удаление записей старше срока."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class RetentionPolicy(Protocol):
    async def retention_days(self) -> int: ...


class AuditPurger(Protocol):
    async def count_older(self, before: datetime) -> int: ...

    async def delete_older(self, before: datetime) -> int: ...
