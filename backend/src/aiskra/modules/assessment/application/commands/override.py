"""Экспертная оценка (п. 4.3): преподаватель ставит балл и комментарий поверх автооценки. Правка пишется в
expert_overrides и в аудит (ТЗ: изменение оценок только с фиксацией в журнале аудита).

Править можно только оценку карточки своего занятия (ТЗ 2.5, как отзыв `SaveFeedback`): чужое занятие или карточка
вне занятия — 404. Порог «зачтено» — из настроек занятия, клиент его не задаёт."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from aiskra.modules.assessment.application.ports.attempts import AssessmentRecord
from aiskra.modules.assessment.application.ports.reports import CardLessons
from aiskra.modules.assessment.domain.scoring import PASS_THRESHOLD
from aiskra.shared.application import Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import DomainError, NotFoundError
from aiskra.shared.security import Principal


class OverrideStore(Protocol):
    async def get(self, assessment_id: UUID) -> AssessmentRecord | None: ...

    async def override(
        self, assessment_id: UUID, *, teacher_id: UUID, score: float, passed: bool, comment: str, before: float
    ) -> None: ...


@dataclass(frozen=True, kw_only=True)
class OverrideAssessment(Command):
    actor: Principal
    assessment_id: UUID
    score: float
    comment: str
    meta: RequestMeta = field(default_factory=RequestMeta)


class OverrideAssessmentHandler:
    def __init__(self, store: OverrideStore, lessons: CardLessons, audit: AuditRecorder, uow: UnitOfWork) -> None:
        self._store = store
        self._lessons = lessons
        self._audit = audit
        self._uow = uow

    async def __call__(self, cmd: OverrideAssessment) -> AssessmentRecord:
        if not 0 <= cmd.score <= 100:
            raise DomainError("Балл — от 0 до 100", code="bad_score")
        if len(cmd.comment.strip()) < 3:
            raise DomainError("Укажите причину правки (комментарий обучающемуся)", code="comment_required")
        rec = await self._store.get(cmd.assessment_id)
        lesson = await self._lessons.lesson_of(rec.card_id) if rec is not None else None
        if rec is None or lesson is None or lesson.teacher_id != cmd.actor.user_id:
            raise NotFoundError("Оценка не найдена", code="assessment_not_found")
        threshold = float(lesson.settings.get("threshold", PASS_THRESHOLD))
        try:
            await self._store.override(
                cmd.assessment_id,
                teacher_id=cmd.actor.user_id,
                score=round(cmd.score, 1),
                passed=cmd.score >= threshold,
                comment=cmd.comment.strip()[:1000],
                before=rec.score,
            )
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.ASSESSMENT_OVERRIDDEN,
                    actor=cmd.actor,
                    meta=cmd.meta,
                    card_number=rec.details.get("card_number"),
                    description=f"{rec.score} → {round(cmd.score, 1)}: {cmd.comment.strip()[:200]}",
                    object_type="assessment",
                    object_id=str(rec.id),
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        updated = await self._store.get(cmd.assessment_id)
        assert updated is not None
        return updated
