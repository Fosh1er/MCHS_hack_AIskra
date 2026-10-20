"""Телефонная книга ДДС в БД: одна строка на службу, записи — JSON-список (не больше 10)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.training.application.ports.phonebook import Phonebook
from aiskra.modules.training.domain.phonebook import PhonebookEntry
from aiskra.modules.training.infrastructure.models import DdsPhonebookModel
from aiskra.platform.types import as_utc


class SqlPhonebookRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, service_code: str) -> Phonebook | None:
        row = await self._s.get(DdsPhonebookModel, service_code)
        if row is None:
            return None
        return Phonebook(
            service_code=row.service_code,
            entries=[PhonebookEntry.from_json(e) for e in row.entries or []],
            updated_at=as_utc(row.updated_at),
            updated_by=row.updated_by,
        )

    async def save(self, book: Phonebook) -> None:
        row = await self._s.get(DdsPhonebookModel, book.service_code)
        if row is None:
            row = DdsPhonebookModel(service_code=book.service_code)
            self._s.add(row)
        row.entries = [e.to_json() for e in book.entries]
        row.updated_by = book.updated_by
        if book.updated_at is not None:
            row.updated_at = book.updated_at
        await self._s.flush()
