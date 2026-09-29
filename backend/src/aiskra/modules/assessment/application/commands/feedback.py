"""Сохранить отзыв преподавателя по занятию (п. 4.7). Автор текста — преподаватель: черновик ИИ становится видимым
обучающемуся только отсюда. Каждое сохранение пишется в журнал аудита."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from aiskra.modules.assessment.application.ports.attempts import AssessmentRepository
from aiskra.modules.assessment.application.ports.feedback import FeedbackRecord, FeedbackStore
from aiskra.modules.assessment.application.ports.reports import SessionFactsSource
from aiskra.modules.assessment.application.queries.feedback import feedback_context
from aiskra.modules.assessment.domain.feedback import MAX_TEXT, MIN_TEXT, similarity
from aiskra.shared.application import Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import DomainError
from aiskra.shared.security import Principal

DraftSource = Literal["ai", "rules"]


@dataclass(frozen=True, kw_only=True)
class SaveFeedback(Command):
    actor: Principal
    session_id: UUID
    student_id: UUID
    text: str
    # с какого черновика начал преподаватель — чтобы видеть, насколько правят черновики ИИ (п. 3.5); None — писал сам
    draft_text: str | None = None
    draft_source: DraftSource | None = None
    draft_model: str | None = None
    meta: RequestMeta = field(default_factory=RequestMeta)


class SaveFeedbackHandler:
    def __init__(
        self,
        source: SessionFactsSource,
        repo: AssessmentRepository,
        store: FeedbackStore,
        audit: AuditRecorder,
        uow: UnitOfWork,
    ) -> None:
        self._source = source
        self._repo = repo
        self._store = store
        self._audit = audit
        self._uow = uow

    async def __call__(self, cmd: SaveFeedback) -> FeedbackRecord:
        text = cmd.text.strip()
        if len(text) < MIN_TEXT:
            raise DomainError(f"Отзыв — не короче {MIN_TEXT} символов", code="feedback_too_short")
        if len(text) > MAX_TEXT:
            raise DomainError(f"Отзыв — не длиннее {MAX_TEXT} символов", code="feedback_too_long")
        ctx = await feedback_context(
            self._source, self._repo, self._store, actor=cmd.actor, session_id=cmd.session_id, student_id=cmd.student_id
        )
        draft: dict[str, object] = {"source": "manual"}
        if cmd.draft_text and cmd.draft_source:
            draft = {
                "source": cmd.draft_source,
                "model": cmd.draft_model,
                "similarity": similarity(cmd.draft_text, text),
            }
        record = FeedbackRecord(
            session_id=cmd.session_id,
            student_id=cmd.student_id,
            teacher_id=cmd.actor.user_id,
            session_title=ctx.facts.title,
            session_started_at=ctx.facts.started_at,
            text=text,
            details={
                # снимок на момент сохранения: следующий отзыв сравнит «подтянуть» с новым результатом (R4.7-07)
                "focus": [x.key for x in ctx.summary.focus],
                "criteria": ctx.summary.criteria,
                "avg_score": ctx.summary.avg_score,
                "draft": draft,
            },
        )
        try:
            saved = await self._store.save(record)
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.FEEDBACK_SAVED,
                    actor=cmd.actor,
                    meta=cmd.meta,
                    description=f"{ctx.person.full_name} · «{ctx.facts.title}»: {text[:200]}",
                    object_type="session",
                    object_id=str(cmd.session_id),
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return saved
