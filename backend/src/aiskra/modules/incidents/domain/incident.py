"""Карточка происшествия как сущность: открытие, сохранение, правила обязательных полей (п. 1.1).

Инструкция АРМ-112 (docs/brief/03 §4): «Минимум для сохранения карточки: тип, адрес (с домом), описание,
ФИО, статус заявителя, пострадавшие». Для нерезультативного вызова («нет контакта», «срыв звонка»)
карточка сохраняется пустой и сразу получает статус «Завершена» (§2.4).
Служебные типы без реагирования (Консультация, Справка, Тестовый вызов…) не дают конечного типа
классификатора, поэтому адрес, заявитель и описание для них не обязательны.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from aiskra.modules.incidents.domain.card import DESCRIPTION_MAX, IncidentCardData
from aiskra.shared.domain import Entity
from aiskra.shared.errors import DomainError


class CardStatus(StrEnum):
    DRAFT = "draft"  # открыта, заполняется
    REGISTERED = "registered"  # «Зарегистрирована» — сохранена, службы оповещены
    WORKED = "worked"  # «Отработана» — оператор закончил работу с карточкой (Alt+S в просмотре)
    CHECKED = "checked"  # «Проверена» — главный специалист (в тренажёре — преподаватель, Alt+Y)
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


# Пауза таймера на подсказки по карточке (п. 5.3): одна на карточку и не дольше — иначе лазейка «остановить время».
MAX_TIMER_PAUSE = timedelta(minutes=10)


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
    is_emergency: bool = False  # ЧС
    is_incident: bool = False  # ЧП
    worked_at: datetime | None = None
    checked_at: datetime | None = None
    checked_by: UUID | None = None
    scenario_id: UUID | None = None  # сценарий входящего вызова (п. 1.4) — эталон для оценки (3.4)
    session_id: UUID | None = None  # занятие (п. 4.2)
    origin: str = "student"  # student | scenario | system
    paused_ms: int | None = None  # п. 5.3: сколько таймер стоял на паузе; None — паузы не было
    pause_started_at: datetime | None = None  # пауза идёт сейчас

    @property
    def processing_ms(self) -> int | None:
        """Таймер карточки: от открытия до сохранения без паузы на обучение интерфейсу (основа оценки тайминга)."""
        if self.saved_at is None:
            return None
        return max(0, int((self.saved_at - self.opened_at).total_seconds() * 1000) - (self.paused_ms or 0))

    def pause_timer(self, now: datetime) -> None:
        """Остановить таймер на время подсказок по карточке (п. 5.3). Одна пауза на карточку."""
        if self.status is not CardStatus.DRAFT:
            raise DomainError(f"Карточка {self.number} уже сохранена", code="card_already_saved")
        if self.pause_started_at is not None:
            return  # уже на паузе — повтор запроса после сбоя связи
        if self.paused_ms is not None:
            raise DomainError("Таймер этой карточки уже останавливался", code="timer_pause_used")
        self.pause_started_at = now

    def resume_timer(self, now: datetime) -> int:
        """Запустить таймер снова. Возвращает, сколько всего таймер стоял на паузе, мс (не больше MAX_TIMER_PAUSE)."""
        if self.pause_started_at is None:
            return self.paused_ms or 0  # паузы нет — повтор запроса
        pause = min(max(now - self.pause_started_at, timedelta(0)), MAX_TIMER_PAUSE)
        self.paused_ms = (self.paused_ms or 0) + int(pause.total_seconds() * 1000)
        self.pause_started_at = None
        return self.paused_ms

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
        self.resume_timer(now)  # сохранили во время паузы — пауза кончилась в момент сохранения
        self.saved_at = now

    # ---------------------------------------------------------------- после сохранения (п. 1.3)

    def _ensure_saved(self) -> None:
        if self.status is CardStatus.DRAFT:
            raise DomainError("Карточка ещё не сохранена", code="card_not_saved")
        if self.status is CardStatus.COMPLETED:
            raise DomainError("Пустая карточка («нет контакта» / «срыв звонка») не изменяется", code="card_completed")

    def mark_worked(self, now: datetime) -> None:
        """«Отработана»: оператор закончил работу с карточкой."""
        if self.status is not CardStatus.REGISTERED:
            raise DomainError("Отработать можно только зарегистрированную карточку", code="bad_card_status")
        self.status = CardStatus.WORKED
        self.worked_at = now

    def mark_checked(self, by: UUID, now: datetime) -> None:
        """«Проверена»: главный специалист (преподаватель) принял отработанную карточку."""
        if self.status is not CardStatus.WORKED:
            raise DomainError("Проверить можно только отработанную карточку", code="bad_card_status")
        self.status = CardStatus.CHECKED
        self.checked_at = now
        self.checked_by = by

    def return_for_rework(self) -> None:
        """«Вернуть на доработку»: карточка снова в работе у оператора."""
        if self.status not in (CardStatus.WORKED, CardStatus.CHECKED):
            raise DomainError("Вернуть можно отработанную или проверенную карточку", code="bad_card_status")
        self.status = CardStatus.REGISTERED
        self.worked_at = None
        self.checked_at = None
        self.checked_by = None

    def set_flags(self, *, emergency: bool, incident: bool) -> list[str]:
        """Признаки ЧС / ЧП (тумблеры режима просмотра). Возвращает изменённые признаки."""
        self._ensure_saved()
        changed = [
            name
            for name, old, new in (("ЧС", self.is_emergency, emergency), ("ЧП", self.is_incident, incident))
            if old != new
        ]
        self.is_emergency, self.is_incident = emergency, incident
        self.data.flags.emergency, self.data.flags.incident = emergency, incident
        return changed

    def append(self, appendix: Appendix) -> list[str]:
        """«Дополнение» (Shift+F2): только пустые поля, дописать описание, пострадавшие (docs/brief/03 §2.12)."""
        self._ensure_saved()
        if self.status is CardStatus.CHECKED:
            raise DomainError("Проверенная карточка не дополняется", code="card_checked")
        changed: list[str] = []
        for key, value in appendix.fields.items():
            if key not in APPENDABLE_FIELDS:
                raise DomainError(f"Поле «{key}» нельзя дополнить", code="field_not_appendable")
            value = value.strip()
            if not value:
                continue
            group, name = key.split(".")
            target = getattr(self.data, group)
            if getattr(target, name):
                raise DomainError(f"Поле «{APPENDABLE_FIELDS[key]}» уже заполнено", code="field_not_empty")
            setattr(target, name, value)
            changed.append(APPENDABLE_FIELDS[key])
        if appendix.description_add.strip():
            text = self.data.description
            text = f"{text}\n{appendix.description_add.strip()}" if text else appendix.description_add.strip()
            if len(text) > DESCRIPTION_MAX:
                raise DomainError(f"Описание длиннее {DESCRIPTION_MAX} символов", code="description_too_long")
            self.data.description = text
            changed.append("описание")
        if appendix.victims_count is not None and appendix.victims_count != self.data.victims.count:
            if appendix.victims_count < 0:
                raise DomainError("Количество пострадавших не может быть отрицательным", code="bad_victims")
            self.data.victims.has = appendix.victims_count > 0
            self.data.victims.count = appendix.victims_count
            changed.append("пострадавшие")
        return changed


APPENDABLE_FIELDS: dict[str, str] = {
    "applicant.name": "ФИО заявителя",
    "phones.provided": "предоставленный номер",
    "phones.on_site": "телефон на место",
    "address.object": "объект",
    "address.flat": "квартира/офис",
    "address.entrance": "подъезд",
    "address.floor": "этаж",
    "address.code": "код",
    "address.descriptive": "описательный адрес",
}


@dataclass(frozen=True, kw_only=True)
class Appendix:
    fields: dict[str, str] = field(default_factory=dict)
    description_add: str = ""
    victims_count: int | None = None


@dataclass(eq=False, kw_only=True)
class Workout(Entity):
    """Отработка (`image70`): звонок оператора после сохранения карточки — в службу или другому адресату."""

    card_id: UUID
    author_id: UUID
    at: datetime
    operator_number: str | None = None
    service_code: str | None = None  # служба из справочника; None — свободный адресат («экипаж», «заявитель»)
    target: str = ""  # название адресата, как в колонке «Служба»
    called_to: str = ""  # «Куда звонили»: дежурный, приёмная…
    phone: str = ""
    receiver: str = ""  # ФИО принявшего
    message: str = ""  # «Суть сообщения»

    def __post_init__(self) -> None:
        if not (self.service_code or self.target.strip()):
            raise DomainError("Укажите службу или адресата звонка", code="bad_workout")
        if not self.message.strip():
            raise DomainError("Укажите суть сообщения", code="bad_workout")
        if len(self.message) > 1000:
            raise DomainError("Суть сообщения — до 1000 символов", code="bad_workout")
