"""Запросы занятий (п. 4.2): список и карточка занятия, «моё занятие» обучающегося, мониторинг в реальном времени."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from aiskra.modules.training.application.ports.sessions import (
    ParticipantProgress,
    SessionMonitorSource,
    SessionRepository,
    StudentDirectory,
    StudentRow,
)
from aiskra.modules.training.domain.session import TrainingSession
from aiskra.shared.application import Query
from aiskra.shared.errors import NotFoundError
from aiskra.shared.security import Principal


@dataclass(frozen=True)
class ParticipantView:
    student_id: UUID
    full_name: str
    login: str
    role: str
    dds_service_code: str | None


@dataclass(frozen=True)
class SessionView:
    id: UUID
    title: str
    mode: str
    card_source: str
    status: str
    groups: list[int]
    settings: dict[str, Any]
    started_at: datetime | None
    finished_at: datetime | None
    participants: list[ParticipantView] = field(default_factory=list)


async def session_view(s: TrainingSession, students: StudentDirectory) -> SessionView:
    names = await students.names([p.student_id for p in s.participants])
    return SessionView(
        id=s.id,
        title=s.title,
        mode=s.mode.value,
        card_source=s.card_source.value,
        status=s.status.value,
        groups=list(s.groups),
        settings=dict(s.settings),
        started_at=s.started_at,
        finished_at=s.finished_at,
        participants=[
            ParticipantView(
                student_id=p.student_id,
                full_name=names[p.student_id].full_name if p.student_id in names else "?",
                login=names[p.student_id].login if p.student_id in names else "",
                role=p.role,
                dds_service_code=p.dds_service_code,
            )
            for p in s.participants
        ],
    )


@dataclass(frozen=True, kw_only=True)
class ListSessions(Query):
    actor: Principal
    page: int = 1
    page_size: int = 30


@dataclass(frozen=True)
class SessionPage:
    items: list[SessionView]
    total: int


class ListSessionsHandler:
    def __init__(self, repo: SessionRepository, students: StudentDirectory) -> None:
        self._repo = repo
        self._students = students

    async def __call__(self, q: ListSessions) -> SessionPage:
        items, total = await self._repo.page(
            teacher_id=q.actor.user_id, limit=q.page_size, offset=(q.page - 1) * q.page_size
        )
        return SessionPage(items=[await session_view(s, self._students) for s in items], total=total)


@dataclass(frozen=True, kw_only=True)
class GetSession(Query):
    actor: Principal
    session_id: UUID


class GetSessionHandler:
    def __init__(self, repo: SessionRepository, students: StudentDirectory) -> None:
        self._repo = repo
        self._students = students

    async def __call__(self, q: GetSession) -> SessionView:
        s = await self._repo.get(q.session_id)
        if s is None or s.teacher_id != q.actor.user_id:
            raise NotFoundError("Занятие не найдено", code="session_not_found")
        return await session_view(s, self._students)


@dataclass(frozen=True, kw_only=True)
class MySession(Query):
    actor: Principal


@dataclass(frozen=True)
class MySessionView:
    session_id: UUID
    title: str
    mode: str
    card_source: str
    role: str
    dds_service_code: str | None
    groups: list[int]
    settings: dict[str, Any]
    started_at: datetime | None


class MySessionHandler:
    def __init__(self, repo: SessionRepository) -> None:
        self._repo = repo

    async def __call__(self, q: MySession) -> MySessionView | None:
        s = await self._repo.running_for_student(q.actor.user_id)
        p = s.participant(q.actor.user_id) if s else None
        if s is None or p is None:
            return None
        return MySessionView(
            session_id=s.id,
            title=s.title,
            mode=s.mode.value,
            card_source=s.card_source.value,
            role=p.role,
            dds_service_code=p.dds_service_code,
            groups=list(s.groups),
            settings=dict(s.settings),
            started_at=s.started_at,
        )


@dataclass(frozen=True, kw_only=True)
class SessionMonitor(Query):
    actor: Principal
    session_id: UUID


@dataclass(frozen=True)
class MonitorRow:
    participant: ParticipantView
    progress: ParticipantProgress


@dataclass(frozen=True)
class MonitorView:
    session: SessionView
    rows: list[MonitorRow]


class SessionMonitorHandler:
    def __init__(self, repo: SessionRepository, students: StudentDirectory, source: SessionMonitorSource) -> None:
        self._repo = repo
        self._students = students
        self._source = source

    async def __call__(self, q: SessionMonitor) -> MonitorView:
        s = await self._repo.get(q.session_id)
        if s is None or s.teacher_id != q.actor.user_id:
            raise NotFoundError("Занятие не найдено", code="session_not_found")
        view = await session_view(s, self._students)
        progress = {p.student_id: p for p in await self._source.progress(s)}
        return MonitorView(
            session=view,
            rows=[
                MonitorRow(
                    participant=p, progress=progress.get(p.student_id) or ParticipantProgress(student_id=p.student_id)
                )
                for p in view.participants
            ],
        )


@dataclass(frozen=True, kw_only=True)
class ListStudents(Query):
    pass


class ListStudentsHandler:
    def __init__(self, students: StudentDirectory) -> None:
        self._students = students

    async def __call__(self, q: ListStudents) -> list[StudentRow]:
        return await self._students.students()
