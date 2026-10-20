"""Самостоятельная тренировка ДДС (п. 2.1, рекомендация экспертов п. 10): учебная карточка без преподавателя.

Обучающийся вне занятия просит карточку для выбранной службы. Система берёт утверждённый сценарий банка, где служба
есть в эталоне служб, а если такого нет — генерирует сценарий на лету (как входящий вызов 112: без модели — офлайн).
Карточка системная, вне занятия, автор — сам обучающийся: её видит только он (`incidents/queries/dds.py:dds_scope`).
Оценка — сразу после окончательного статуса (`POST /assessment/cards/{id}/evaluate`), с рекомендациями."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from aiskra.modules.training.application.commands.scenarios import ScenarioGenerator
from aiskra.modules.training.application.ports.scenarios import ScenarioRepository
from aiskra.modules.training.application.ports.sessions import SelfTrainingCards, ServiceSwitches, SessionRepository
from aiskra.modules.training.domain.self_training import (
    GENERATE_ATTEMPTS,
    MAX_SELF_WAITING,
    pick_for_service,
    reference_services,
    self_training_rng,
)
from aiskra.shared.application import Clock, Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import DomainError, NotFoundError
from aiskra.shared.security import Principal


@dataclass(frozen=True, kw_only=True)
class RequestDdsSelfCard(Command):
    actor: Principal  # обучающийся вне занятия
    service_code: str
    seed: int | None = None  # для тестов; по умолчанию — от пользователя и времени
    meta: RequestMeta = field(default_factory=RequestMeta)


@dataclass(frozen=True)
class SelfCardIssued:
    card_id: UUID
    card_number: int
    scenario_id: UUID
    generated: bool  # сценарий создан на лету (банк без подходящего) — ждёт проверки преподавателем
    waiting: int  # ожидающих решения учебных карточек вместе с новой


class RequestDdsSelfCardHandler:
    def __init__(
        self,
        sessions: SessionRepository,
        scenarios: ScenarioRepository,
        cards: SelfTrainingCards,
        generator: ScenarioGenerator,
        audit: AuditRecorder,
        uow: UnitOfWork,
        clock: Clock,
        switches: ServiceSwitches | None = None,
    ) -> None:
        self._sessions = sessions
        self._scenarios = scenarios
        self._cards = cards
        self._gen = generator
        self._audit = audit
        self._uow = uow
        self._clock = clock
        self._switches = switches

    async def __call__(self, cmd: RequestDdsSelfCard) -> SelfCardIssued:
        if self._switches and not await self._switches.enabled("dds_feed"):
            raise DomainError("Выдача карточек в ДДС остановлена администратором", code="service_stopped")
        code = cmd.service_code.strip()
        if not code or not await self._cards.service_exists(code):
            raise NotFoundError("Нет такой службы", code="service_not_found")
        if await self._sessions.running_for_student(cmd.actor.user_id) is not None:
            raise DomainError(
                "На занятии карточки в ДДС выдаёт занятие — самостоятельная тренировка доступна вне занятия",
                code="in_session",
            )
        waiting, recent = await self._cards.pending(cmd.actor.user_id)
        if waiting >= MAX_SELF_WAITING:
            raise DomainError(
                f"Ждут решения {waiting} учебные карточки — примите по ним решение, затем возьмите новую",
                code="self_queue_full",
            )
        now = self._clock.now()
        rng = self_training_rng(cmd.actor.user_id, now, cmd.seed)
        try:
            picked = pick_for_service(await self._cards.approved_references(), code, rng, recent)
            scenario = await self._scenarios.get(picked) if picked else None
            generated = scenario is None
            if scenario is None:  # подходящего в банке нет — на лету, черновиком на проверку преподавателю
                for _ in range(GENERATE_ATTEMPTS):
                    scenario = await self._gen.generate(rng, [], 2, None)
                    if code in reference_services(scenario.reference_card):
                        break
                assert scenario is not None
                await self._scenarios.add(scenario)
            card_id, number = await self._cards.create(scenario, service_code=code, student_id=cmd.actor.user_id)
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.DDS_SELF_CARD,
                    actor=cmd.actor,
                    meta=cmd.meta,
                    description=f"Карточка № {number} для службы {code}"
                    + (" (сценарий создан на лету)" if generated else ""),
                    object_type="incident_card",
                    object_id=str(card_id),
                    data={"service_code": code, "scenario_id": str(scenario.id), "generated": generated},
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return SelfCardIssued(
            card_id=card_id, card_number=number, scenario_id=scenario.id, generated=generated, waiting=waiting + 1
        )
