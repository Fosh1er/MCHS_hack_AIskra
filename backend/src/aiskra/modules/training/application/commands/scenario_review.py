"""Частичное утверждение эталона (п. 3.3): решения преподавателя по разделам — «принят» или «на доработку».

Все разделы приняты — сценарий утверждён и попадает в занятия; иначе он на проверке (утверждённый сценарий с разделом
на доработке из банка занятий снимается). Правила разделов и отпечатков — `domain/review.py`."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from aiskra.modules.training.application.ports.scenarios import ScenarioRepository
from aiskra.modules.training.domain.review import SECTIONS, Decision, SectionReview, all_accepted, mark_sections
from aiskra.modules.training.domain.review import review_state as sections_of
from aiskra.modules.training.domain.scenario import ScenarioStatus
from aiskra.shared.application import Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import DomainError, NotFoundError
from aiskra.shared.security import Principal

TITLES = {Decision.ACCEPTED: "принят", Decision.REWORK: "на доработку"}


@dataclass(frozen=True, kw_only=True)
class ReviewSections(Command):
    actor: Principal
    scenario_id: UUID
    sections: dict[str, tuple[Decision, str]]  # раздел → решение и комментарий
    meta: RequestMeta = field(default_factory=RequestMeta)


@dataclass(frozen=True)
class SectionsReviewed:
    status: str
    sections: list[SectionReview]


class ReviewSectionsHandler:
    def __init__(self, repo: ScenarioRepository, audit: AuditRecorder, uow: UnitOfWork) -> None:
        self._repo = repo
        self._audit = audit
        self._uow = uow

    async def __call__(self, cmd: ReviewSections) -> SectionsReviewed:
        s = await self._repo.get(cmd.scenario_id)
        if s is None:
            raise NotFoundError("Сценарий не найден", code="scenario_not_found")
        if s.status is ScenarioStatus.ARCHIVED:
            raise DomainError("Сценарий в архиве", code="scenario_archived")
        mark_sections(s, cmd.sections, by=str(cmd.actor.user_id))
        if all_accepted(s):
            s.approve(cmd.actor.user_id)
        else:
            s.status = ScenarioStatus.DRAFT
            s.approved_by = None
        state = sections_of(s)
        accepted = sum(r.decision == Decision.ACCEPTED for r in state)
        marked = "; ".join(
            f"{SECTIONS[k]} — {TITLES[d]}" + (f": {c}" if c.strip() else "") for k, (d, c) in cmd.sections.items()
        )
        try:
            await self._repo.save(s)
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.SCENARIO_APPROVED
                    if s.status is ScenarioStatus.APPROVED
                    else AuditEvent.SCENARIO_REVIEWED,
                    actor=cmd.actor,
                    meta=cmd.meta,
                    description=f"{s.title}: принято разделов {accepted} из {len(state)}. {marked}"[:1000],
                    object_type="scenario",
                    object_id=str(s.id),
                    data={k: d.value for k, (d, _) in cmd.sections.items()},
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return SectionsReviewed(status=s.status.value, sections=state)
