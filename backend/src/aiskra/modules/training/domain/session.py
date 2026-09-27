"""Занятие (п. 4.2): тип, категории событий, источник карточек, участники по ролям, нормативы и темп потока.

ТЗ, сценарии 2–3: преподаватель выбирает категории (группы классификатора), запускает занятие, завершает в любой
момент. Роль обучающегося — оператор 112 или диспетчер ДДС конкретной службы (#624: одна учётка, две мини-роли).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from aiskra.shared.errors import DomainError


class SessionMode(StrEnum):
    CARDS_112 = "cards_112"  # ТЗ сценарий 2: имитация звонков, заполнение карточек
    DDS_ACTIONS = "dds_actions"  # ТЗ сценарий 3: действия с карточками в ДДС
    MIXED = "mixed"


class CardSource(StrEnum):
    GENERATED = "generated"  # карточки от системы по сценариям
    TRAINEE = "trainee"  # карточки, заполненные операторами 112 этого занятия
    MIXED = "mixed"


class SessionStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    FINISHED = "finished"


DEFAULT_SETTINGS: dict[str, Any] = {
    "norm_112": 75,  # норматив опроса до готовой карточки, с (ПП РФ № 1931, п. 9 «р»)
    "norm_dds": 30,  # норматив решения ДДС, с (ТЗ: по умолчанию 30 с)
    "threshold": 70,  # порог «зачтено»
    "difficulty": 2,
    "call_interval_s": 40,  # темп входящих вызовов для 112
    "feed_interval_s": 45,  # темп системных карточек для ДДС
    "max_waiting": 3,  # сколько карточек одновременно ждут в очереди ДДС (#706)
}


@dataclass
class Participant:
    student_id: UUID
    role: str  # 112 | dds
    dds_service_code: str | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if self.role not in ("112", "dds"):
            raise DomainError("Роль участника — 112 или dds", code="bad_role")
        if self.role == "dds" and not self.dds_service_code:
            raise DomainError("Для роли ДДС укажите службу", code="service_required")


@dataclass
class TrainingSession:
    title: str
    mode: SessionMode
    card_source: CardSource
    teacher_id: UUID
    groups: list[int] = field(default_factory=list)
    participants: list[Participant] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)
    status: SessionStatus = SessionStatus.PLANNED
    started_at: datetime | None = None
    finished_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise DomainError("Название занятия не может быть пустым", code="empty_title")
        self.settings = {**DEFAULT_SETTINGS, **self.settings}
        for key in ("norm_112", "norm_dds", "call_interval_s", "feed_interval_s"):
            if not 5 <= float(self.settings[key]) <= 3600:
                raise DomainError(f"Параметр {key} — от 5 до 3600 с", code="bad_setting")
        if not 1 <= int(self.settings["difficulty"]) <= 5 or not 0 <= float(self.settings["threshold"]) <= 100:
            raise DomainError("Сложность 1–5, порог 0–100", code="bad_setting")

    def participant(self, student_id: UUID) -> Participant | None:
        return next((p for p in self.participants if p.student_id == student_id), None)

    def start(self, now: datetime) -> None:
        if self.status is not SessionStatus.PLANNED:
            raise DomainError("Занятие уже запущено или завершено", code="session_not_planned")
        if not self.participants:
            raise DomainError("Добавьте обучающихся", code="no_participants")
        if self.mode is SessionMode.CARDS_112 and not any(p.role == "112" for p in self.participants):
            raise DomainError("Для занятия «Карточки 112» нужен хотя бы один оператор 112", code="no_operator")
        if self.mode is SessionMode.DDS_ACTIONS and not any(p.role == "dds" for p in self.participants):
            raise DomainError("Для занятия «Действия ДДС» нужен хотя бы один диспетчер ДДС", code="no_dds")
        self.status = SessionStatus.RUNNING
        self.started_at = now

    def finish(self, now: datetime) -> None:
        if self.status is not SessionStatus.RUNNING:
            raise DomainError("Занятие не идёт", code="session_not_running")
        self.status = SessionStatus.FINISHED
        self.finished_at = now

    @property
    def system_cards(self) -> bool:
        """Выпускает ли система карточки в очереди ДДС (ТЗ сценарий 3: «сгенерированные системой карточки»)."""
        return self.card_source in (CardSource.GENERATED, CardSource.MIXED)
