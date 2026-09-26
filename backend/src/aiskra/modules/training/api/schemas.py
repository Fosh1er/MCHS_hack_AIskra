"""Pydantic-схемы API training."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from aiskra.modules.training.domain.call import CallParty


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
