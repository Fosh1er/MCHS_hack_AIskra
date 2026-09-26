"""SQL-хранилище оценок (таблица assessments из 0.2): роль, служба и обучающийся — в details."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.assessment.application.ports.attempts import AssessmentRecord
from aiskra.modules.assessment.infrastructure.models import AssessmentModel
from aiskra.platform.types import as_utc


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
