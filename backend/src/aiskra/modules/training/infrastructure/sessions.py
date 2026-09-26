"""SQL-хранилище занятий: training_sessions (+ категории в settings.groups) и участники — assignments (из 0.2)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Uuid, column, delete, func, select, table
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.training.application.ports.sessions import StudentRow
from aiskra.modules.training.domain.session import CardSource, Participant, SessionMode, SessionStatus, TrainingSession
from aiskra.modules.training.infrastructure.models import AssignmentModel, TrainingSessionModel
from aiskra.platform.types import as_utc

_users = table(
    "users",
    column("id", Uuid),
    column("login"),
    column("full_name"),
    column("role"),
    column("operator_number"),
    column("status"),
)


class SqlSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, s: TrainingSession) -> None:
        row = TrainingSessionModel(id=s.id, teacher_id=s.teacher_id)
        self._fill(row, s)
        self._s.add(row)
        await self._s.flush()
        await self._participants(s)

    async def save(self, s: TrainingSession) -> None:
        row = await self._s.get(TrainingSessionModel, s.id)
        if row is None:
            raise LookupError(f"Занятие {s.id} не найдено")
        self._fill(row, s)
        await self._s.flush()

    @staticmethod
    def _fill(row: TrainingSessionModel, s: TrainingSession) -> None:
        row.title = s.title
        row.mode = s.mode.value
        row.card_source = s.card_source.value
        row.settings = {**s.settings, "groups": list(s.groups)}
        row.status = s.status.value
        row.started_at = s.started_at
        row.finished_at = s.finished_at

    async def _participants(self, s: TrainingSession) -> None:
        await self._s.execute(delete(AssignmentModel).where(AssignmentModel.session_id == s.id))
        for p in s.participants:
            self._s.add(
                AssignmentModel(
                    id=p.id,
                    session_id=s.id,
                    student_id=p.student_id,
                    role=p.role,
                    dds_service_code=p.dds_service_code,
                    status="assigned",
                )
            )
        await self._s.flush()

    async def _entity(self, row: TrainingSessionModel) -> TrainingSession:
        parts = (await self._s.execute(select(AssignmentModel).where(AssignmentModel.session_id == row.id))).scalars()
        settings = dict(row.settings or {})
        groups = [int(g) for g in settings.pop("groups", [])]
        return TrainingSession(
            id=row.id,
            title=row.title,
            mode=SessionMode(row.mode),
            card_source=CardSource(row.card_source),
            teacher_id=row.teacher_id,
            groups=groups,
            settings=settings,
            status=SessionStatus(row.status),
            started_at=as_utc(row.started_at),
            finished_at=as_utc(row.finished_at),
            participants=[
                Participant(id=a.id, student_id=a.student_id, role=a.role, dds_service_code=a.dds_service_code)
                for a in parts
            ],
        )

    async def get(self, session_id: UUID) -> TrainingSession | None:
        row = await self._s.get(TrainingSessionModel, session_id)
        return await self._entity(row) if row else None

    async def page(self, *, teacher_id: UUID | None, limit: int, offset: int) -> tuple[list[TrainingSession], int]:
        stmt = select(TrainingSessionModel)
        if teacher_id:
            stmt = stmt.where(TrainingSessionModel.teacher_id == teacher_id)
        total = int((await self._s.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one())
        rows = (
            (await self._s.execute(stmt.order_by(TrainingSessionModel.created_at.desc()).limit(limit).offset(offset)))
            .scalars()
            .all()
        )
        return [await self._entity(r) for r in rows], total

    async def for_student(self, student_id: UUID) -> list[TrainingSession]:
        rows = (
            (
                await self._s.execute(
                    select(TrainingSessionModel)
                    .join(AssignmentModel, AssignmentModel.session_id == TrainingSessionModel.id)
                    .where(AssignmentModel.student_id == student_id)
                    .order_by(TrainingSessionModel.created_at.desc())
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
        return [await self._entity(r) for r in rows]

    async def running_for_student(self, student_id: UUID) -> TrainingSession | None:
        row = (
            (
                await self._s.execute(
                    select(TrainingSessionModel)
                    .join(AssignmentModel, AssignmentModel.session_id == TrainingSessionModel.id)
                    .where(AssignmentModel.student_id == student_id, TrainingSessionModel.status == "running")
                    .order_by(TrainingSessionModel.started_at.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        return await self._entity(row) if row else None


class SqlStudentDirectory:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def students(self) -> list[StudentRow]:
        rows = (
            await self._s.execute(
                select(_users.c.id, _users.c.login, _users.c.full_name, _users.c.operator_number)
                .where(_users.c.role == "student", _users.c.status == "active")
                .order_by(_users.c.full_name)
            )
        ).all()
        return [StudentRow(id=r[0], login=r[1], full_name=r[2], operator_number=r[3]) for r in rows]

    async def names(self, ids: list[UUID]) -> dict[UUID, StudentRow]:
        if not ids:
            return {}
        rows = (
            await self._s.execute(
                select(_users.c.id, _users.c.login, _users.c.full_name, _users.c.operator_number).where(
                    _users.c.id.in_(ids)
                )
            )
        ).all()
        return {r[0]: StudentRow(id=r[0], login=r[1], full_name=r[2], operator_number=r[3]) for r in rows}
