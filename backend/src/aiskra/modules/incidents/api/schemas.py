"""Pydantic-схемы API карточки 112. Повторяют `domain/card.py:IncidentCardData` (JSON-эталон, docs/brief/03 §4),
чтобы структура была видна в OpenAPI и проверялась на входе."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from aiskra.modules.incidents.domain.card import AMBULANCE_VISIBLE_CHARS, DESCRIPTION_MAX, ApplicantStatus
from aiskra.modules.incidents.domain.dds import ServiceStatus


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PhonesIn(_Strict):
    aon: str = Field(default="", max_length=32, description="АОН — из телефонии, не редактируется")
    provided: str = Field(default="", max_length=32, description="Предоставленный номер (со слов)")
    on_site: str = Field(default="", max_length=32, description="Телефон на место")
    foreign: bool = Field(default=False, description="Зарубежный номер (не +7)")


class ApplicantIn(_Strict):
    name: str = Field(default="", max_length=255)
    status: ApplicantStatus | None = None
    foreign_language: bool = False


class VictimsIn(_Strict):
    has: bool = False
    count: int = Field(default=0, ge=0, le=10_000)


class AddressIn(_Strict):
    raw: str = Field(default="", max_length=500)
    country: str = Field(default="Россия", max_length=64)
    region: str = Field(default="Москва", max_length=128)
    city: str = Field(default="Москва", max_length=128)
    object: str = Field(default="", max_length=255)
    okrug: str | None = Field(default=None, max_length=8)
    district: str | None = Field(default=None, max_length=64)
    street: str = Field(default="", max_length=255)
    house: str = Field(default="", max_length=32)
    building: str = Field(default="", max_length=32)
    structure: str = Field(default="", max_length=32)
    flat: str = Field(default="", max_length=32)
    entrance: str = Field(default="", max_length=16)
    floor: str = Field(default="", max_length=16)
    code: str = Field(default="", max_length=32)
    descriptive: str = Field(default="", max_length=1000)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)


class FlagsIn(_Strict):
    no_contact: bool = False
    call_dropped: bool = False
    refusal_103: bool = False
    emergency: bool = False
    incident: bool = False


class CardDataIn(_Strict):
    phones: PhonesIn = PhonesIn()
    channel: str | None = Field(default=None, max_length=32)
    applicant: ApplicantIn = ApplicantIn()
    victims: VictimsIn = VictimsIn()
    card_types: list[str] = Field(default_factory=list, max_length=20, description="«Что случилось?» (dict_card_types)")
    incident_types: list[str] = Field(default_factory=list, max_length=20, description="Конечные типы классификатора")
    questionnaire: dict[str, dict[str, Any]] = Field(default_factory=dict, description="{тип: {вопрос: ответ}}")
    card_flags: list[str] = Field(default_factory=list, max_length=30, description="Признаки (enums.card_flag)")
    address: AddressIn = AddressIn()
    description: str = Field(
        default="",
        max_length=DESCRIPTION_MAX,
        description=f"Описание со слов заявителя; служба 03 видит первые {AMBULANCE_VISIBLE_CHARS} символов",
    )
    services: list[str] = Field(default_factory=list, description="Заполняется сервером из списка служб")
    flags: FlagsIn = FlagsIn()


class OpenCardIn(_Strict):
    aon: str = Field(default="", max_length=32)
    channel: str | None = Field(default=None, max_length=32)
    scenario_id: UUID | None = Field(default=None, description="Сценарий учебного входящего вызова (п. 1.4)")


class CardOpenedOut(BaseModel):
    id: UUID
    number: int
    opened_at: datetime


class CardServiceIn(_Strict):
    code: str = Field(max_length=64)
    is_main: bool = False
    added_by: str = Field(default="auto", pattern="^(auto|manual)$")
    service_type: str | None = Field(default=None, max_length=500)


class SaveCardIn(_Strict):
    data: CardDataIn
    services: list[CardServiceIn] = Field(default_factory=list, max_length=60)


class CardServiceOut(BaseModel):
    code: str
    is_main: bool
    added_by: str
    service_type: str | None = None


class CardSavedOut(BaseModel):
    id: UUID
    number: int
    status: str
    saved_at: datetime
    processing_ms: int
    services: list[CardServiceOut]


# ------------------------------------------------------------------ п. 1.3: после сохранения


class CardFlagsIn(_Strict):
    emergency: bool
    incident: bool


class AppendIn(_Strict):
    fields: dict[str, str] = Field(
        default_factory=dict, description="Только пустые поля: applicant.name, phones.*, address.*"
    )
    description_add: str = Field(default="", max_length=DESCRIPTION_MAX)
    victims_count: int | None = Field(default=None, ge=0, le=10_000)


class WorkoutIn(_Strict):
    service_code: str | None = Field(default=None, max_length=64)
    target: str = Field(default="", max_length=255, description="Адресат, если это не служба: «экипаж», «заявитель»")
    called_to: str = Field(default="", max_length=255)
    phone: str = Field(default="", max_length=32)
    receiver: str = Field(default="", max_length=255)
    message: str = Field(max_length=1000)


class StatusCommentIn(_Strict):
    comment: str = Field(default="", max_length=500)


class StatusOut(BaseModel):
    status: str


class ChangedOut(BaseModel):
    changed: list[str]


class CreatedOut(BaseModel):
    id: UUID


# ------------------------------------------------------------------ п. 2.2: АРМ ДДС


class ServiceStatusIn(_Strict):
    status: ServiceStatus
    order_no: str = Field(default="", max_length=32, description="«Номер наряда»")
    comment: str = Field(default="", max_length=500)
