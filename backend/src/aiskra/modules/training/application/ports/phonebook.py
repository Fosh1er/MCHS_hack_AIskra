"""Порт телефонной книги ДДС (п. 2.3, рекомендация экспертов): абоненты IP-телефона службы."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from aiskra.modules.training.domain.phonebook import PhonebookEntry


@dataclass(frozen=True)
class Phonebook:
    service_code: str
    entries: list[PhonebookEntry]
    updated_at: datetime | None = None
    updated_by: UUID | None = None


class PhonebookRepository(Protocol):
    async def get(self, service_code: str) -> Phonebook | None: ...

    async def save(self, book: Phonebook) -> None: ...
