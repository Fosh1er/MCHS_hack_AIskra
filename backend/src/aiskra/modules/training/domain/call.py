"""Учебный звонок (п. 1.4, 2.3): входящий вызов заявителя в 112, звонки ДДС старшему группы, заявителю,
в смежную службу. Реплики сохраняются — по ним оценка (3.4) проверяет, что спросил оператор и когда звонил."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

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


@dataclass
class CallMessage:
    call_id: UUID
    speaker: Speaker
    text: str
    at: datetime
    id: UUID = field(default_factory=uuid4)


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
    id: UUID = field(default_factory=uuid4)

    def answer(self, now: datetime) -> None:
        if self.status is CallStatus.ENDED:
            raise DomainError("Звонок уже завершён", code="call_ended")
        if self.status is CallStatus.RINGING:
            self.status = CallStatus.ACTIVE
            self.answered_at = now

    def end(self, now: datetime) -> None:
        if self.status is not CallStatus.ENDED:
            self.status = CallStatus.ENDED
            self.ended_at = now

    def ensure_active(self) -> None:
        if self.status is CallStatus.ENDED:
            raise DomainError("Звонок завершён — наберите снова", code="call_ended")
