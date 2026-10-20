"""Телефонная книга ДДС для экрана преподавателя и IP-телефона диспетчера (п. 2.3)."""

from __future__ import annotations

from dataclasses import dataclass

from aiskra.modules.training.application.ports.phonebook import Phonebook, PhonebookRepository
from aiskra.shared.application import Query


@dataclass(frozen=True, kw_only=True)
class GetPhonebook(Query):
    service_code: str


class GetPhonebookHandler:
    def __init__(self, books: PhonebookRepository) -> None:
        self._books = books

    async def __call__(self, q: GetPhonebook) -> Phonebook | None:
        """Книги нет — `None`: телефон ДДС работает по-прежнему (старший группы, заявитель, смежные службы)."""
        return await self._books.get(q.service_code.strip())
