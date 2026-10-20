"""Телефонная книга ДДС (п. 2.3, рекомендация экспертов): преподаватель задаёт абонентов IP-телефона службы.

PUT заменяет список целиком; правила — `domain/phonebook.py:validate_entries` (≤10 записей, уникальные номера)."""

from __future__ import annotations

from dataclasses import dataclass, field

from aiskra.modules.training.application.ports.phonebook import Phonebook, PhonebookRepository
from aiskra.modules.training.domain.phonebook import PhonebookEntry, validate_entries
from aiskra.shared.application import Clock, Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import DomainError
from aiskra.shared.security import Principal


@dataclass(frozen=True, kw_only=True)
class SavePhonebook(Command):
    actor: Principal
    service_code: str
    entries: list[PhonebookEntry]
    meta: RequestMeta = field(default_factory=RequestMeta)


class SavePhonebookHandler:
    def __init__(self, books: PhonebookRepository, audit: AuditRecorder, uow: UnitOfWork, clock: Clock) -> None:
        self._books = books
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def __call__(self, cmd: SavePhonebook) -> Phonebook:
        code = cmd.service_code.strip()
        if not code or len(code) > 64:
            raise DomainError("Не указана служба", code="phonebook_bad_service")
        entries = validate_entries(cmd.entries)
        before = await self._books.get(code)
        was = len(before.entries) if before else 0
        book = Phonebook(service_code=code, entries=entries, updated_at=self._clock.now(), updated_by=cmd.actor.user_id)
        await self._books.save(book)
        await self._audit.record(
            AuditEntry(
                event=AuditEvent.DDS_PHONEBOOK_SAVED,
                actor=cmd.actor,
                meta=cmd.meta,
                description=f"Телефонная книга ДДС {code}: {len(entries)} абон. (было {was})",
                object_type="dds_phonebook",
                object_id=code,
                data={"entries": [e.to_json() for e in entries]},
            )
        )
        try:
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return book
