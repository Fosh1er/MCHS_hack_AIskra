"""Учебный звонок (п. 1.4, 2.3): входящий вызов заявителя в 112, звонки ДДС старшему группы, заявителю,
в смежную службу. Реплики сохраняются — по ним оценка (3.4) проверяет, что спросил оператор и когда звонил."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from aiskra.modules.training.domain.tone import CallerTone, ToneSnapshot
from aiskra.shared.errors import DomainError


class CallParty(StrEnum):
    APPLICANT = "applicant"  # заявитель (легенда сценария)
    BRIGADE = "brigade"  # старший группы реагирования своей службы
    SERVICE = "service"  # диспетчер смежной службы


class CallStatus(StrEnum):
    RINGING = "ringing"
    ACTIVE = "active"
    ENDED = "ended"


class Speaker(StrEnum):
    OPERATOR = "operator"
    PARTY = "party"
    SYSTEM = "system"


class ReplicaVia(StrEnum):
    """Как оператор сказал реплику (п. 3.6): в голосовом режиме в время карточки входит речь собеседника."""

    TEXT = "text"
    VOICE = "voice"  # кнопка «говорить»
    HANDS_FREE = "hands_free"


_VIA_RANK = {ReplicaVia.TEXT: 0, ReplicaVia.VOICE: 1, ReplicaVia.HANDS_FREE: 2}


def call_mode(vias: list[ReplicaVia]) -> ReplicaVia | None:
    """Режим звонка — самый «голосовой» из способов реплик оператора; реплик не было — режима нет."""
    return max(vias, key=_VIA_RANK.__getitem__) if vias else None


@dataclass
class CallMessage:
    call_id: UUID
    speaker: Speaker
    text: str
    at: datetime
    tone: ToneSnapshot | None = None  # состояние заявителя у его реплики (п. 3.6): по нему озвучивается реплика
    via: ReplicaVia | None = None  # у реплик оператора: напечатал, сказал кнопкой или без рук
    id: UUID = field(default_factory=uuid4)
    meta: dict[str, Any] | None = None  # п. 3.7: действия оператора, состояние заявителя, ремарки, голос


@dataclass
class Call:
    student_id: UUID
    role: str  # 112 | dds
    party: CallParty
    direction: str  # in | out
    started_at: datetime
    scenario_id: UUID | None = None
    card_id: UUID | None = None
    service_code: str | None = None  # своя ДДС (для звонков из АРМ ДДС)
    target_service: str | None = None  # вызываемая смежная служба
    aon: str = ""
    status: CallStatus = CallStatus.RINGING
    answered_at: datetime | None = None
    ended_at: datetime | None = None
    revealed: list[str] = field(default_factory=list)  # темы легенды, которые заявитель уже раскрыл
    tone: CallerTone | None = None  # состояние заявителя (п. 3.6); у старшего группы и службы — нет
    psy: dict[str, Any] | None = None  # п. 3.7: снимок профиля заявителя и текущее состояние (ADR-0012)
    ended_by: str | None = None  # operator | party — кто завершил звонок
    id: UUID = field(default_factory=uuid4)

    def answer(self, now: datetime) -> None:
        if self.status is CallStatus.ENDED:
            raise DomainError("Звонок уже завершён", code="call_ended")
        if self.status is CallStatus.RINGING:
            self.status = CallStatus.ACTIVE
            self.answered_at = now

    def end(self, now: datetime, by: str = "operator") -> None:
        if self.status is not CallStatus.ENDED:
            self.status = CallStatus.ENDED
            self.ended_at = now
            self.ended_by = by

    def ensure_active(self) -> None:
        if self.status is CallStatus.ENDED:
            raise DomainError("Звонок завершён — наберите снова", code="call_ended")
