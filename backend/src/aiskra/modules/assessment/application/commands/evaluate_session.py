"""Оценить все карточки занятия (п. 4.3): карточки операторов 112 и работу каждой ДДС-участника.
Уже оценённые пересчитываются новой версией (эталон и правила могли измениться); экспертная правка сохраняется
в истории версий."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from aiskra.modules.assessment.application.commands.assess import AssessCard, AssessCardHandler, Settings
from aiskra.modules.assessment.application.ports.reports import SessionFactsSource
from aiskra.modules.assessment.application.queries.reports import cards_of
from aiskra.modules.assessment.domain.scoring import CARD_NORM_SECONDS, DDS_NORM_SECONDS
from aiskra.shared.application import Command
from aiskra.shared.audit import RequestMeta
from aiskra.shared.errors import DomainError, NotFoundError
from aiskra.shared.security import Principal


@dataclass(frozen=True, kw_only=True)
class EvaluateSession(Command):
    actor: Principal
    session_id: UUID
    meta: RequestMeta = field(default_factory=RequestMeta)


@dataclass(frozen=True)
class EvaluateSummary:
    assessed: int
    skipped: int


class EvaluateSessionHandler:
    def __init__(self, source: SessionFactsSource, assess: AssessCardHandler) -> None:
        self._source = source
        self._assess = assess

    async def __call__(self, cmd: EvaluateSession) -> EvaluateSummary:
        facts = await self._source.session(cmd.session_id)
        if facts is None or facts.teacher_id != cmd.actor.user_id:
            raise NotFoundError("Занятие не найдено", code="session_not_found")
        st = facts.settings
        assessed = skipped = 0
        for p in facts.participants:
            settings = Settings(
                norm_seconds=float(
                    st.get(
                        "norm_112" if p.role == "112" else "norm_dds",
                        CARD_NORM_SECONDS if p.role == "112" else DDS_NORM_SECONDS,
                    )
                ),
                threshold=float(st.get("threshold", 70)),
            )
            for card in cards_of(p, facts.cards):
                if p.role == "dds" and card.services.get(p.service_code or "") in ("added", None):
                    skipped += 1  # ДДС ещё не открывала карточку — оценивать нечего
                    continue
                try:
                    await self._assess(
                        AssessCard(
                            actor=cmd.actor,
                            card_id=card.card_id,
                            role=p.role,
                            service_code=p.service_code if p.role == "dds" else None,
                            settings=settings,
                            meta=cmd.meta,
                        )
                    )
                    assessed += 1
                except (DomainError, NotFoundError):
                    skipped += 1
        return EvaluateSummary(assessed=assessed, skipped=skipped)
