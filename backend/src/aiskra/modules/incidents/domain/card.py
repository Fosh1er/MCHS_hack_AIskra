"""Структура карточки происшествия АРМ-112 (JSON-эталон, docs/brief/03 §4; specs/0.2 §4).

Одна структура используется для трёх целей: заполняемая обучающимся карточка (п. 1.1), эталон сценария
(п. 3.2) и сравнение при оценке (п. 3.4). Хранится в incident_cards.payload / scenarios.reference_card.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from aiskra.shared.errors import DomainError

DESCRIPTION_MAX = 1999  # счётчик «N / 1999» в блоке «Описание со слов заявителя»
AMBULANCE_VISIBLE_CHARS = 100  # в службу 03 передаются только первые 100 символов описания


class ApplicantStatus(StrEnum):
    """Статус заявителя — строго одно из 6 значений (коды совпадают с data/dictionaries/enums.yaml)."""

    WITNESS = "witness"
    VICTIM = "victim"
    RELATIVE = "relative"
    ACQUAINTANCE = "acquaintance"
    CHILD = "child"
    PARTICIPANT = "participant"


@dataclass
class Phones:
    aon: str = ""  # АОН — автоматически, не редактируется
    provided: str = ""  # предоставленный номер (со слов)
    on_site: str = ""  # телефон на место
    foreign: bool = False  # зарубежный номер (не +7)


@dataclass
class Applicant:
    name: str = ""
    status: ApplicantStatus | None = None
    foreign_language: bool = False


@dataclass
class Victims:
    has: bool = False
    count: int = 0

    def __post_init__(self) -> None:
        if self.count < 0:
            raise DomainError("Количество пострадавших не может быть отрицательным", code="bad_victims")
        if not self.has and self.count:
            raise DomainError("Количество указано при «Пострадавшие: Нет»", code="bad_victims")


@dataclass
class Address:
    raw: str = ""
    country: str = "Россия"
    region: str = "Москва"
    city: str = "Москва"
    object: str = ""
    okrug: str | None = None  # код округа (dict_okrugs)
    district: str | None = None  # код района/поселения (dict_districts)
    street: str = ""
    house: str = ""
    building: str = ""  # корпус
    structure: str = ""  # строение/сооружение
    flat: str = ""
    entrance: str = ""
    floor: str = ""
    code: str = ""  # код домофона
    descriptive: str = ""  # описательный адрес
    lat: float | None = None
    lon: float | None = None


@dataclass
class CardFlags:
    no_contact: bool = False
    call_dropped: bool = False
    refusal_103: bool = False  # отказ от реагирования скорой (только для 103)
    emergency: bool = False  # ЧС
    incident: bool = False  # ЧП


@dataclass
class IncidentCardData:
    phones: Phones = field(default_factory=Phones)
    channel: str | None = None  # код канала связи (enums.channel)
    applicant: Applicant = field(default_factory=Applicant)
    victims: Victims = field(default_factory=Victims)
    card_types: list[str] = field(default_factory=list)  # «Что случилось?» (dict_card_types)
    incident_types: list[str] = field(default_factory=list)  # конечные типы классификатора
    questionnaire: dict[str, dict[str, Any]] = field(default_factory=dict)  # {card_type: {вопрос: ответ}}
    card_flags: list[str] = field(default_factory=list)  # признаки маршрутизации (enums.card_flag)
    address: Address = field(default_factory=Address)
    description: str = ""
    services: list[str] = field(default_factory=list)  # коды dict_services
    flags: CardFlags = field(default_factory=CardFlags)

    def __post_init__(self) -> None:
        if len(self.description) > DESCRIPTION_MAX:
            raise DomainError(f"Описание длиннее {DESCRIPTION_MAX} символов", code="description_too_long")
        if self.flags.refusal_103 and "103" not in self.card_types:
            raise DomainError("Отказ от реагирования возможен только для типа 103", code="refusal_not_103")

    @property
    def ambulance_excerpt(self) -> str:
        """То, что увидит служба 03: первые 100 символов описания."""
        return self.description[:AMBULANCE_VISIBLE_CHARS]

    @property
    def is_empty_call(self) -> bool:
        """«Нет контакта» / «Срыв звонка» — карточка сохраняется пустой."""
        return self.flags.no_contact or self.flags.call_dropped

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        status = self.applicant.status
        data["applicant"]["status"] = status.value if status else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IncidentCardData:
        applicant = dict(data.get("applicant") or {})
        if applicant.get("status"):
            try:
                applicant["status"] = ApplicantStatus(applicant["status"])
            except ValueError as exc:
                raise DomainError(f"Неизвестный статус заявителя: {applicant['status']}", code="bad_applicant") from exc
        return cls(
            phones=Phones(**(data.get("phones") or {})),
            channel=data.get("channel"),
            applicant=Applicant(**applicant),
            victims=Victims(**(data.get("victims") or {})),
            card_types=list(data.get("card_types") or []),
            incident_types=list(data.get("incident_types") or []),
            questionnaire=dict(data.get("questionnaire") or {}),
            card_flags=list(data.get("card_flags") or []),
            address=Address(**(data.get("address") or {})),
            description=data.get("description") or "",
            services=list(data.get("services") or []),
            flags=CardFlags(**(data.get("flags") or {})),
        )
