"""Pydantic-схемы API training."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from aiskra.modules.training.domain.call import CallParty, ReplicaVia
from aiskra.modules.training.domain.session import CardSource, SessionMode
from aiskra.modules.training.domain.tone import ToneSnapshot


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GenerateIn(_Strict):
    count: int = Field(default=5, ge=1, le=50)
    groups: list[int] = Field(default_factory=list, description="Группы классификатора; пусто — любые")
    difficulty: int = Field(default=2, ge=1, le=5)


class GeneratedOut(BaseModel):
    ids: list[UUID]


class StatusOut(BaseModel):
    status: str


class IncomingIn(_Strict):
    groups: list[int] = Field(default_factory=list)
    difficulty: int | None = Field(default=None, ge=1, le=5, description="Сложность занятия; нет — любая")


class AnswerIn(_Strict):
    card_id: UUID | None = None


class DdsCallIn(_Strict):
    card_id: UUID
    service_code: str = Field(max_length=64, description="Своя ДДС")
    party: CallParty
    target_service: str | None = Field(default=None, max_length=64)
    incoming: bool = Field(default=False, description="Входящий доклад старшего группы")


class ReplicaIn(_Strict):
    text: str = Field(min_length=1, max_length=500)
    via: ReplicaVia = Field(
        default=ReplicaVia.TEXT, description="Как сказана: text, voice (кнопка), hands_free (п. 3.6)"
    )
    # п. 3.6: сигналы голосового канала — передаёт голосовой или дуплекс-адаптер; в текстовом режиме не нужны
    latency_ms: int | None = Field(default=None, ge=0, le=600_000, description="Пауза перед ответом оператора, мс")
    interrupted: bool = Field(default=False, description="Оператор перебил реплику заявителя")


class ReplicaOut(BaseModel):
    speaker: str
    text: str
    message_id: UUID | None = None
    tone: ToneSnapshot | None = Field(
        default=None, description="Состояние заявителя у этой реплики (п. 3.6): эмоция, шкалы 0–10, подача, причины"
    )
    remarks: list[str] = Field(default_factory=list, description="Ремарки заявителя: плачет, кричит… (п. 3.7)")
    voice: dict[str, object] | None = Field(
        default=None, description="Параметры голоса реплики для синтеза речи (п. 3.6, руководство §7)"
    )
    hung_up: bool = Field(default=False, description="Заявитель положил трубку")


class SectionDecisionIn(_Strict):
    decision: Literal["accepted", "rework"]
    comment: str = Field(default="", max_length=500, description="Что доработать; для «на доработку» обязателен")


class ReviewSectionsIn(_Strict):
    sections: dict[str, SectionDecisionIn] = Field(
        min_length=1, description="Раздел эталона (story, applicant, classification, services, dds) → решение"
    )


class EditScenarioIn(_Strict):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    opening: str | None = Field(default=None, min_length=3, max_length=500)
    what: str | None = Field(default=None, min_length=3, max_length=1000)
    details: str | None = Field(default=None, max_length=2000)
    comment: str | None = Field(
        default=None, min_length=3, max_length=1000, description="Перегенерировать моделью по комментарию"
    )


class ParticipantBody(_Strict):
    student_id: UUID
    role: str = Field(pattern="^(112|dds)$")
    dds_service_code: str | None = Field(default=None, max_length=64)


class SessionSettingsIn(_Strict):
    """Пустое поле — значение по умолчанию из настроек администратора (GET /training/session-defaults)."""

    norm_112: float | None = Field(default=None, ge=5, le=3600)
    norm_dds: float | None = Field(default=None, ge=5, le=3600)
    threshold: float | None = Field(default=None, ge=0, le=100)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    call_interval_s: float | None = Field(default=None, ge=5, le=3600)
    feed_interval_s: float | None = Field(default=None, ge=5, le=3600)
    max_waiting: int | None = Field(default=None, ge=1, le=10)
    psy: PsySettingsIn | None = None


class PsySettingsIn(_Strict):
    """Психологический модификатор занятия (п. 3.7, ADR-0012)."""

    enabled: bool = False
    share: float = Field(default=0.3, ge=0, le=1, description="Доля звонков с психологическим профилем заявителя")
    profiles: list[str] | Literal["auto"] = Field(default="auto", description="Профили; auto — по сложности сценария")
    intensity: int = Field(default=2, ge=1, le=3)
    weight: float = Field(default=0, ge=0, le=1, description="Вес блока «Работа с заявителем» в итоговом балле")
    sensitive: list[str] = Field(default_factory=list, description="Явно разрешённые кризисные профили")
    llm_acts: bool = Field(default=False, description="Разметка действий оператора моделью (PSY_ACTS)")


class ScenarioPsyIn(_Strict):
    profile: str | None = Field(default=None, max_length=32, description="Профиль заявителя; null — снять")


class PsyProfileOut(BaseModel):
    id: str
    title: str
    group: str
    sensitive: bool
    pinned_only: bool
    start: int
    floor: int
    pool: int
    key_acts: list[str]
    critical: list[str]
    required_routing: list[str]
    speech: dict[int, str]
    sources: list[str]


class CreateSessionIn(_Strict):
    title: str = Field(min_length=3, max_length=200)
    mode: SessionMode
    card_source: CardSource = CardSource.GENERATED
    groups: list[int] = Field(default_factory=list, description="Категории событий — группы классификатора")
    participants: list[ParticipantBody] = Field(default_factory=list, max_length=100)
    settings: SessionSettingsIn = Field(default_factory=SessionSettingsIn)


class CreatedOut(BaseModel):
    id: UUID
