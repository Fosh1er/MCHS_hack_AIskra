"""Телефонная книга ДДС (рекомендация экспертов к п. 2.3): абоненты IP-телефона диспетчера.

Перечень и условные номера задаёт преподаватель — не больше 10 записей на службу. Абоненты — должностные лица
(руководитель организации, начальник отдела реагирования, начальник и специалист аварийной бригады). Общение ДДС
с заявителем исключено; звонить ему можно, только если в книге есть запись «заявитель» — тогда номер берётся из
карточки. Номер не из книги — «Номер не обслуживается», звонок не начинается."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from aiskra.shared.errors import DomainError

MAX_ENTRIES = 10
NAME_MAX = 120
NUMBER_RE = re.compile(r"^\+?[0-9][0-9 ()-]{1,23}$")
NOT_SERVED = "Номер не обслуживается"


class ContactRole(StrEnum):
    HEAD = "head"  # руководитель организации
    RESPONSE_CHIEF = "response_chief"  # начальник отдела реагирования
    BRIGADE_CHIEF = "brigade_chief"  # начальник аварийной бригады
    BRIGADE_SPECIALIST = "brigade_specialist"  # специалист аварийной бригады
    APPLICANT = "applicant"  # заявитель — номер из карточки


ROLE_TITLES: dict[ContactRole, str] = {
    ContactRole.HEAD: "Руководитель организации",
    ContactRole.RESPONSE_CHIEF: "Начальник отдела реагирования",
    ContactRole.BRIGADE_CHIEF: "Начальник аварийной бригады",
    ContactRole.BRIGADE_SPECIALIST: "Специалист аварийной бригады",
    ContactRole.APPLICANT: "Заявитель (номер из карточки)",
}


@dataclass(frozen=True)
class PhonebookEntry:
    role: ContactRole
    name: str = ""
    number: str = ""  # у записи «заявитель» номера нет: он в карточке

    @property
    def title(self) -> str:
        return ROLE_TITLES[self.role]

    def to_json(self) -> dict[str, str]:
        return {"role": self.role.value, "name": self.name, "number": self.number}

    @classmethod
    def from_json(cls, raw: dict[str, str]) -> PhonebookEntry:
        return cls(role=ContactRole(raw["role"]), name=raw.get("name", ""), number=raw.get("number", ""))


def digits(number: str) -> str:
    """Ключ сравнения номеров: только цифры (пробелы, скобки, дефисы и «+» не важны)."""
    return re.sub(r"\D", "", number or "")


def validate_entries(entries: list[PhonebookEntry]) -> list[PhonebookEntry]:
    """Правила книги: ≤10 записей, номер обязателен и уникален (кроме «заявителя»), «заявитель» — не больше одного."""
    if len(entries) > MAX_ENTRIES:
        raise DomainError(f"В книге службы не больше {MAX_ENTRIES} номеров", code="phonebook_too_long")
    clean: list[PhonebookEntry] = []
    seen: set[str] = set()
    applicant = False
    for i, e in enumerate(entries, 1):
        name = " ".join(e.name.split())
        if len(name) > NAME_MAX:
            raise DomainError(f"Строка {i}: ФИО длиннее {NAME_MAX} символов", code="phonebook_bad_name")
        if e.role is ContactRole.APPLICANT:
            if applicant:
                raise DomainError("Запись «заявитель» в книге может быть только одна", code="phonebook_applicant_twice")
            applicant = True
            clean.append(PhonebookEntry(ContactRole.APPLICANT, name, ""))
            continue
        number = " ".join(e.number.split())
        if not NUMBER_RE.match(number):
            raise DomainError(f"Строка {i}: укажите номер — цифры, от 2 знаков", code="phonebook_bad_number")
        key = digits(number)
        if key in seen:
            raise DomainError(f"Номер {number} в книге повторяется", code="phonebook_duplicate_number")
        seen.add(key)
        if not name:
            raise DomainError(f"Строка {i}: укажите ФИО абонента", code="phonebook_bad_name")
        clean.append(PhonebookEntry(e.role, name, number))
    return clean


def resolve_number(entries: list[PhonebookEntry], dialed: str, applicant_phone: str) -> PhonebookEntry | None:
    """Кого набрал диспетчер: абонент книги, заявитель (номер из карточки, если «заявитель» есть в книге) или никто."""
    key = digits(dialed)
    if not key:
        return None
    for e in entries:
        if e.role is not ContactRole.APPLICANT and digits(e.number) == key:
            return e
    applicant = next((e for e in entries if e.role is ContactRole.APPLICANT), None)
    card = digits(applicant_phone)
    if applicant is not None and card and (card == key or (len(key) >= 10 and card[-10:] == key[-10:])):
        return applicant
    return None


def contact_greeting(entry: PhonebookEntry) -> str:
    """Абонент книги снимает трубку: должность и фамилия."""
    surname = entry.name.split()[0] if entry.name else ""
    return f"{entry.title}{', ' + surname if surname else ''}, слушаю."


def contact_reply(entry: PhonebookEntry, base: str) -> str:
    """Офлайн-ответ абонента книги: обращение по должности поверх доклада старшего группы."""
    return f"{entry.title}{' ' + entry.name if entry.name else ''}. {base}"
