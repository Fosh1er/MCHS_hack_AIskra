"""Команды занятий (п. 4.2): создать, начать, завершить; выпустить системную карточку в очередь ДДС."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from uuid import UUID

from aiskra.modules.training.application.ports.psy import PsyCatalog
from aiskra.modules.training.application.ports.scenarios import ScenarioRepository
from aiskra.modules.training.application.ports.sessions import SessionDefaults, SessionRepository, SystemCards
from aiskra.modules.training.domain.psy import check_settings
from aiskra.modules.training.domain.session import CardSource, Participant, SessionMode, TrainingSession
from aiskra.shared.application import Clock, Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import DomainError, NotFoundError
from aiskra.shared.security import Principal


@dataclass(frozen=True)
class ParticipantIn:
    student_id: UUID
    role: str
    dds_service_code: str | None = None


@dataclass(frozen=True, kw_only=True)
class CreateSession(Command):
    actor: Principal
    title: str
    mode: SessionMode
    card_source: CardSource
    groups: list[int] = field(default_factory=list)
    participants: list[ParticipantIn] = field(default_factory=list)
    settings: dict[str, object] = field(default_factory=dict)
    meta: RequestMeta = field(default_factory=RequestMeta)


class _Base:
    def __init__(self, repo: SessionRepository, audit: AuditRecorder, uow: UnitOfWork, clock: Clock) -> None:
        self._repo = repo
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def _commit(self, entry: AuditEntry | None = None) -> None:
        try:
            if entry:
                await self._audit.record(entry)
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise

    async def _own(self, session_id: UUID, actor: Principal) -> TrainingSession:
        s = await self._repo.get(session_id)
        if s is None or s.teacher_id != actor.user_id:
            raise NotFoundError("Занятие не найдено", code="session_not_found")
        return s


class CreateSessionHandler(_Base):
    def __init__(
        self,
        repo: SessionRepository,
        audit: AuditRecorder,
        uow: UnitOfWork,
        clock: Clock,
        defaults: SessionDefaults | None = None,
        catalog: PsyCatalog | None = None,
    ) -> None:
        super().__init__(repo, audit, uow, clock)
        self._defaults = defaults
        self._catalog = catalog

    async def __call__(self, cmd: CreateSession) -> UUID:
        seen: set[UUID] = set()
        participants = []
        for p in cmd.participants:
            if p.student_id in seen:
                raise DomainError("Обучающийся указан дважды", code="duplicate_participant")
            seen.add(p.student_id)
            participants.append(Participant(student_id=p.student_id, role=p.role, dds_service_code=p.dds_service_code))
        session = TrainingSession(
            title=cmd.title.strip(),
            mode=cmd.mode,
            card_source=cmd.card_source,
            teacher_id=cmd.actor.user_id,
            groups=list(cmd.groups),
            participants=participants,
            settings={**(await self._defaults.get() if self._defaults else {}), **cmd.settings},
        )
        if self._catalog is not None:  # п. 3.7: профили модификатора — только из каталога
            try:
                check_settings(session.settings["psy"], set(self._catalog.profiles()))
            except ValueError as e:
                raise DomainError(str(e), code="bad_psy_setting") from e
        psy = session.settings["psy"]
        await self._repo.add(session)
        await self._commit(
            AuditEntry(
                event=AuditEvent.SESSION_CREATED,
                actor=cmd.actor,
                meta=cmd.meta,
                description=session.title
                + (f" (психологический модификатор: доля {psy['share']:.0%})" if psy.get("enabled") else ""),
                object_type="training_session",
                object_id=str(session.id),
                data={"psy": psy} if psy.get("enabled") else {},
            )
        )
        return session.id


@dataclass(frozen=True, kw_only=True)
class ChangeSessionState(Command):
    actor: Principal
    session_id: UUID
    start: bool  # True — начать, False — завершить
    meta: RequestMeta = field(default_factory=RequestMeta)


class ChangeSessionStateHandler(_Base):
    async def __call__(self, cmd: ChangeSessionState) -> str:
        s = await self._own(cmd.session_id, cmd.actor)
        if cmd.start:
            s.start(self._clock.now())
        else:
            s.finish(self._clock.now())
        await self._repo.save(s)
        await self._commit(
            AuditEntry(
                event=AuditEvent.SESSION_STARTED if cmd.start else AuditEvent.SESSION_FINISHED,
                actor=cmd.actor,
                meta=cmd.meta,
                description=s.title,
                object_type="training_session",
                object_id=str(s.id),
            )
        )
        return s.status.value


@dataclass(frozen=True, kw_only=True)
class FeedDdsCard(Command):
    actor: Principal  # обучающийся-ДДС
    seed: int | None = None


@dataclass(frozen=True)
class FeedResult:
    card_id: UUID | None
    waiting: int
    reason: str = ""


class FeedDdsCardHandler:
    """Поток карточек в ДДС по темпу занятия: не чаще `feed_interval_s` и не больше `max_waiting` ожидающих.
    Страница ДДС обучающегося вызывает команду периодически; решение о выпуске — здесь (сервер — источник правды)."""

    def __init__(
        self,
        sessions: SessionRepository,
        scenarios: ScenarioRepository,
        cards: SystemCards,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._sessions = sessions
        self._scenarios = scenarios
        self._cards = cards
        self._uow = uow
        self._clock = clock

    async def __call__(self, cmd: FeedDdsCard) -> FeedResult:
        s = await self._sessions.running_for_student(cmd.actor.user_id)
        p = s.participant(cmd.actor.user_id) if s else None
        if s is None or p is None or p.role != "dds" or not p.dds_service_code:
            return FeedResult(card_id=None, waiting=0, reason="нет занятия с ролью ДДС")
        if not s.system_cards:
            return FeedResult(card_id=None, waiting=0, reason="карточки приходят от операторов 112 занятия")
        waiting, last = await self._cards.waiting(p.dds_service_code, s.id)
        now = self._clock.now()
        if waiting >= int(s.settings["max_waiting"]):
            return FeedResult(card_id=None, waiting=waiting, reason="очередь заполнена")
        if last and (now - last).total_seconds() < float(s.settings["feed_interval_s"]):
            return FeedResult(card_id=None, waiting=waiting, reason="рано")
        scenario = await self._scenarios.random_approved(
            random.Random(cmd.seed),
            s.groups or None,
            int(s.settings["difficulty"]) if "difficulty" in s.settings else None,
        )
        if scenario is None:
            return FeedResult(
                card_id=None, waiting=waiting, reason="в банке нет утверждённых сценариев выбранных категорий"
            )
        try:
            card_id = await self._cards.create_from_scenario(
                scenario, extra_service=p.dds_service_code, session_id=s.id, author_id=s.teacher_id
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return FeedResult(card_id=card_id, waiting=waiting + 1)
