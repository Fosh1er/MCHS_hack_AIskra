"""Pydantic-схемы API training."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from aiskra.modules.training.domain.call import CallParty
from aiskra.modules.training.domain.session import CardSource, SessionMode


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
    difficulty: int = Field(default=2, ge=1, le=5)


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


class ReplicaOut(BaseModel):
    speaker: str
    text: str


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


class CreateSessionIn(_Strict):
    title: str = Field(min_length=3, max_length=200)
    mode: SessionMode
    card_source: CardSource = CardSource.GENERATED
    groups: list[int] = Field(default_factory=list, description="Категории событий — группы классификатора")
    participants: list[ParticipantBody] = Field(default_factory=list, max_length=100)
    settings: SessionSettingsIn = Field(default_factory=SessionSettingsIn)


class CreatedOut(BaseModel):
    id: UUID
