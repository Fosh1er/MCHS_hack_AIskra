"""Телефонная книга ДДС (п. 2.3): правила книги, разбор набранного номера, сохранение с аудитом."""

import asyncio
from uuid import uuid4

import pytest

from aiskra.modules.training.application.commands.phonebook import SavePhonebook, SavePhonebookHandler
from aiskra.modules.training.application.ports.phonebook import Phonebook
from aiskra.modules.training.domain.phonebook import (
    MAX_ENTRIES,
    NOT_SERVED,
    ContactRole,
    PhonebookEntry,
    contact_greeting,
    contact_reply,
    resolve_number,
    validate_entries,
)
from aiskra.shared.errors import DomainError
from aiskra.shared.security import Principal, Role
from tests.unit.identity_fakes import FakeAudit, FakeUow, FixedClock

HEAD = PhonebookEntry(ContactRole.HEAD, "Громов  Пётр Ильич", "100-01")
CHIEF = PhonebookEntry(ContactRole.BRIGADE_CHIEF, "Сомов Илья Петрович", "+7 (495) 100-03")
APPLICANT = PhonebookEntry(ContactRole.APPLICANT, "", "")


def codes(entries: list[PhonebookEntry]) -> str:
    with pytest.raises(DomainError) as e:
        validate_entries(entries)
    return e.value.code


def test_limits_and_uniqueness() -> None:
    many = [PhonebookEntry(ContactRole.BRIGADE_SPECIALIST, f"Абонент {i}", f"200-{i:02d}") for i in range(11)]
    assert len(validate_entries(many[:MAX_ENTRIES])) == MAX_ENTRIES
    assert codes(many) == "phonebook_too_long"
    assert codes([HEAD, PhonebookEntry(ContactRole.RESPONSE_CHIEF, "Иванов И. И.", "10001")]) == (
        "phonebook_duplicate_number"  # номера сравниваются по цифрам
    )
    assert codes([PhonebookEntry(ContactRole.HEAD, "Громов", "")]) == "phonebook_bad_number"
    assert codes([PhonebookEntry(ContactRole.HEAD, "", "100")]) == "phonebook_bad_name"
    assert codes([APPLICANT, APPLICANT]) == "phonebook_applicant_twice"
    clean = validate_entries([HEAD, APPLICANT])
    assert clean[0].name == "Громов Пётр Ильич" and clean[1].number == ""  # номер заявителя — из карточки


def test_resolve_number() -> None:
    book = [HEAD, CHIEF, APPLICANT]
    assert resolve_number(book, "10001", "") == HEAD
    assert resolve_number(book, "84951000 3", "") is None  # другие цифры — не абонент
    assert resolve_number(book, "+74951000 3", "") == CHIEF
    assert resolve_number(book, "8 (917) 980-54-13", "+7 917 980-54-13") == APPLICANT  # последние 10 цифр
    assert resolve_number([HEAD], "+7 917 980-54-13", "+7 917 980-54-13") is None  # заявителя нет в книге
    assert resolve_number(book, "555", "+7 917 980-54-13") is None
    assert resolve_number(book, "", "") is None
    assert NOT_SERVED == "Номер не обслуживается"


def test_contact_speaks_by_role() -> None:
    assert contact_greeting(CHIEF) == "Начальник аварийной бригады, Сомов, слушаю."
    assert contact_reply(CHIEF, "Выехали.") == "Начальник аварийной бригады Сомов Илья Петрович. Выехали."


class MemoryBooks:
    def __init__(self) -> None:
        self.books: dict[str, Phonebook] = {}

    async def get(self, service_code: str) -> Phonebook | None:
        return self.books.get(service_code)

    async def save(self, book: Phonebook) -> None:
        self.books[book.service_code] = book


def test_save_replaces_and_audits() -> None:
    books, audit, uow = MemoryBooks(), FakeAudit(), FakeUow()
    handler = SavePhonebookHandler(books, audit, uow, FixedClock())
    actor = Principal(user_id=uuid4(), session_id=uuid4(), login="t", full_name="Преподаватель", role=Role.TEACHER)
    asyncio.run(handler(SavePhonebook(actor=actor, service_code="S101", entries=[HEAD, CHIEF])))
    asyncio.run(handler(SavePhonebook(actor=actor, service_code="S101", entries=[CHIEF])))
    assert [e.role for e in books.books["S101"].entries] == [ContactRole.BRIGADE_CHIEF]  # заменяется целиком
    assert audit.events == ["dds.phonebook_saved", "dds.phonebook_saved"] and uow.commits == 2
    assert "1 абон. (было 2)" in audit.entries[1].description
    with pytest.raises(DomainError):
        asyncio.run(handler(SavePhonebook(actor=actor, service_code=" ", entries=[])))
