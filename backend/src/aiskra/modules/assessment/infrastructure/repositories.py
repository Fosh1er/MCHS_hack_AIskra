"""SQL-хранилище оценок (таблица assessments из 0.2): роль, служба и обучающийся — в details."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.assessment.application.ports.attempts import AssessmentRecord
from aiskra.modules.assessment.application.ports.feedback import FeedbackRecord
from aiskra.modules.assessment.infrastructure.models import AssessmentModel, ExpertOverrideModel, TeacherFeedbackModel
from aiskra.platform.types import as_utc
from aiskra.shared.domain import utcnow


def _record(r: AssessmentModel) -> AssessmentRecord:
    d = dict(r.details or {})
    sid = d.get("student_id")
    return AssessmentRecord(
        id=r.id,
        card_id=r.card_id or UUID(int=0),
        student_id=UUID(sid) if sid else None,
        role=d.get("role", "112"),
        service_code=d.get("service_code"),
        score=float(r.score or 0),
        passed=bool(d.get("passed")),
        grader=r.grader,
        details=d,
        created_at=as_utc(r.created_at),
    )


class SqlAssessmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, record: AssessmentRecord) -> None:
        prev = await self.latest(record.card_id, record.role, record.service_code)
        details = {
            **record.details,
            "student_id": str(record.student_id) if record.student_id else None,
            "passed": record.passed,
        }
        self._s.add(
            AssessmentModel(
                id=record.id,
                card_id=record.card_id,
                version=(prev.details.get("version", 1) + 1) if prev else 1,
                status="final",
                score=record.score,
                details={**details, "version": (prev.details.get("version", 1) + 1) if prev else 1},
                grader=record.grader,
            )
        )
        await self._s.flush()

    async def latest(self, card_id: UUID, role: str, service_code: str | None) -> AssessmentRecord | None:
        rows = (
            await self._s.execute(
                select(AssessmentModel)
                .where(AssessmentModel.card_id == card_id)
                .order_by(AssessmentModel.created_at.desc(), AssessmentModel.version.desc())
            )
        ).scalars()
        for r in rows:
            d = r.details or {}
            if d.get("role") == role and (role != "dds" or d.get("service_code") == service_code):
                return _record(r)
        return None

    async def recent(self, limit: int) -> list[AssessmentRecord]:
        rows = (
            await self._s.execute(select(AssessmentModel).order_by(AssessmentModel.created_at.desc()).limit(limit))
        ).scalars()
        return [_record(r) for r in rows]

    async def get(self, assessment_id: UUID) -> AssessmentRecord | None:
        row = await self._s.get(AssessmentModel, assessment_id)
        return _record(row) if row else None

    async def override(
        self, assessment_id: UUID, *, teacher_id: UUID, score: float, passed: bool, comment: str, before: float
    ) -> None:
        row = await self._s.get(AssessmentModel, assessment_id)
        if row is None:
            raise LookupError(f"Оценка {assessment_id} не найдена")
        self._s.add(
            ExpertOverrideModel(
                assessment_id=assessment_id,
                teacher_id=teacher_id,
                reason=comment,
                changes={"score": [before, score], "passed": passed},
            )
        )
        row.score = score
        row.grader = "expert"
        row.status = "final"
        row.details = {
            **(row.details or {}),
            "passed": passed,
            "expert": {"score": score, "comment": comment, "teacher_id": str(teacher_id), "auto_score": before},
        }
        await self._s.flush()


def _feedback(r: TeacherFeedbackModel) -> FeedbackRecord:
    return FeedbackRecord(
        session_id=r.session_id,
        student_id=r.student_id,
        teacher_id=r.teacher_id,
        session_title=r.session_title,
        session_started_at=as_utc(r.session_started_at),
        text=r.text,
        details=dict(r.details or {}),
        created_at=as_utc(r.created_at),
        updated_at=as_utc(r.updated_at),
    )


class SqlFeedbackStore:
    """Отзывы преподавателя (п. 4.7), таблица `teacher_feedback`."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def _row(self, session_id: UUID, student_id: UUID) -> TeacherFeedbackModel | None:
        return (
            await self._s.execute(
                select(TeacherFeedbackModel).where(
                    TeacherFeedbackModel.session_id == session_id, TeacherFeedbackModel.student_id == student_id
                )
            )
        ).scalar_one_or_none()

    async def get(self, session_id: UUID, student_id: UUID) -> FeedbackRecord | None:
        row = await self._row(session_id, student_id)
        return _feedback(row) if row else None

    async def for_session(self, session_id: UUID) -> dict[UUID, FeedbackRecord]:
        rows = (
            await self._s.execute(select(TeacherFeedbackModel).where(TeacherFeedbackModel.session_id == session_id))
        ).scalars()
        return {r.student_id: _feedback(r) for r in rows}

    async def for_student(self, student_id: UUID) -> list[FeedbackRecord]:
        rows = (
            await self._s.execute(select(TeacherFeedbackModel).where(TeacherFeedbackModel.student_id == student_id))
        ).scalars()
        # от новых занятий к старым; занятие без времени начала — по времени отзыва
        return sorted(
            (_feedback(r) for r in rows),
            key=lambda f: f.session_started_at or f.created_at or utcnow(),
            reverse=True,
        )

    async def save(self, record: FeedbackRecord) -> FeedbackRecord:
        row = await self._row(record.session_id, record.student_id)
        now = utcnow()
        if row is None:
            row = TeacherFeedbackModel(session_id=record.session_id, student_id=record.student_id, created_at=now)
            self._s.add(row)
        row.teacher_id = record.teacher_id
        row.session_title = record.session_title[:255]
        row.session_started_at = record.session_started_at
        row.text = record.text
        row.details = record.details
        row.updated_at = now
        await self._s.flush()
        return _feedback(row)
