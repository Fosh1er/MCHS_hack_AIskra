"""Карточка происшествия как сущность: открытие, сохранение, правила обязательных полей (п. 1.1).

Инструкция АРМ-112 (docs/brief/03 §4): «Минимум для сохранения карточки: тип, адрес (с домом), описание,
ФИО, статус заявителя, пострадавшие». Для нерезультативного вызова («нет контакта», «срыв звонка»)
карточка сохраняется пустой и сразу получает статус «Завершена» (§2.4).
Служебные типы без реагирования (Консультация, Справка, Тестовый вызов…) не дают конечного типа
классификатора, поэтому адрес, заявитель и описание для них не обязательны.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from aiskra.modules.incidents.domain.card import IncidentCardData
from aiskra.shared.domain import Entity
from aiskra.shared.errors import DomainError


class CardStatus(StrEnum):
    DRAFT = "draft"  # открыта, заполняется
    REGISTERED = "registered"  # «Зарегистрирована» — сохранена, службы оповещены
    COMPLETED = "completed"  # «Завершена» — пустая карточка нерезультативного вызова


class AddedBy(StrEnum):
    AUTO = "auto"  # подобрана автоматически по классификатору и адресу
    MANUAL = "manual"  # добавлена оператором через «+»


@dataclass(frozen=True, kw_only=True)
class CardService:
    code: str
    is_main: bool = False
    added_by: AddedBy = AddedBy.AUTO
    service_type: str | None = None


def missing_for_save(data: IncidentCardData, services: list[CardService]) -> list[str]:
    """Незаполненные обязательные блоки — названиями, как на экране карточки."""
    if data.is_empty_call:
        return []
    missing: list[str] = []
    if not data.card_types:
        missing.append("Что случилось")
    if data.incident_types:  # есть реагирование по классификатору
        a = data.address
        if not (a.house or a.descriptive.strip() or (a.lat is not None and a.lon is not None)):
            missing.append("Адрес (дом, описательный адрес или координаты)")
        if not data.applicant.name.strip():
            missing.append("Фамилия и имя заявителя")
        if data.applicant.status is None:
            missing.append("Статус заявителя")
        if not data.description.strip():
            missing.append("Описание со слов заявителя")
        if not services:
            missing.append("Службы")
    return missing


@dataclass(eq=False, kw_only=True)
class IncidentCard(Entity):
    author_id: UUID
    opened_at: datetime
    number: int = 0  # присваивает хранилище при добавлении («Происшествие 36900001»)
    operator_number: str | None = None
    arm_number: str | None = None
    status: CardStatus = CardStatus.DRAFT
    data: IncidentCardData = field(default_factory=IncidentCardData)
    services: list[CardService] = field(default_factory=list)
    saved_at: datetime | None = None

    @property
    def processing_ms(self) -> int | None:
        """Таймер карточки: от открытия до сохранения (основа оценки тайминга)."""
        if self.saved_at is None:
            return None
        return max(0, int((self.saved_at - self.opened_at).total_seconds() * 1000))

    def save(self, data: IncidentCardData, services: list[CardService], now: datetime) -> None:
        if self.status is not CardStatus.DRAFT:
            raise DomainError(f"Карточка {self.number} уже сохранена", code="card_already_saved")
        codes = [s.code for s in services]
        if len(codes) != len(set(codes)):
            raise DomainError("Служба указана дважды", code="duplicate_service")
        missing = missing_for_save(data, services)
        if missing:
            raise DomainError("Не заполнено: " + "; ".join(missing), code="card_incomplete")
        self.data = data
        self.services = [] if data.is_empty_call else list(services)
        self.data.services = [s.code for s in self.services]
        self.status = CardStatus.COMPLETED if data.is_empty_call else CardStatus.REGISTERED
        self.saved_at = now
