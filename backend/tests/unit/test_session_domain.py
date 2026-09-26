"""П. 4.2–4.3: инварианты занятия и расчёты отчёта (без БД)."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from aiskra.modules.assessment.application.ports.reports import ReportCard, ReportParticipant
from aiskra.modules.assessment.application.queries.reports import cards_of
from aiskra.modules.training.domain.session import CardSource, Participant, SessionMode, SessionStatus, TrainingSession
from aiskra.shared.errors import DomainError

NOW = datetime(2026, 9, 26, 10, tzinfo=UTC)


def make(mode: SessionMode = SessionMode.MIXED, **kw: object) -> TrainingSession:
    return TrainingSession(title="Занятие", mode=mode, card_source=CardSource.GENERATED, teacher_id=uuid4(), **kw)  # type: ignore[arg-type]


def test_defaults_and_validation() -> None:
    s = make(settings={"norm_112": 120})
    assert s.settings["norm_112"] == 120 and s.settings["norm_dds"] == 30 and s.system_cards
    with pytest.raises(DomainError):
        make(settings={"feed_interval_s": 1})
    with pytest.raises(DomainError):
        make(settings={"difficulty": 9})
    with pytest.raises(DomainError):
        Participant(student_id=uuid4(), role="dds")  # служба обязательна
    with pytest.raises(DomainError):
        Participant(student_id=uuid4(), role="teacher")


def test_start_requires_roles_for_mode() -> None:
    s = make(SessionMode.DDS_ACTIONS, participants=[Participant(student_id=uuid4(), role="112")])
    with pytest.raises(DomainError, match="ДДС"):
        s.start(NOW)
    with pytest.raises(DomainError):
        make().start(NOW)  # без участников
    s = make(participants=[Participant(student_id=uuid4(), role="112")])
    s.start(NOW)
    assert s.status is SessionStatus.RUNNING and s.started_at == NOW
    with pytest.raises(DomainError):
        s.start(NOW)
    s.finish(NOW)
    assert s.status is SessionStatus.FINISHED
    with pytest.raises(DomainError):
        s.finish(NOW)


def test_cards_of_participant() -> None:
    op, dds = uuid4(), uuid4()
    card = lambda author, origin, services, status="registered": ReportCard(  # noqa: E731
        card_id=uuid4(),
        number=1,
        author_id=author,
        origin=origin,
        status=status,
        saved_at=NOW,
        processing_s=60,
        card_types=["101"],
        services=services,
    )
    own, draft, system = (
        card(op, "student", {}),
        card(op, "student", {}, "draft"),
        card(uuid4(), "system", {"DDS_01": "added"}),
    )
    cards = [own, draft, system]
    assert cards_of(ReportParticipant(op, "Оператор", "112", None), cards) == [own]
    assert cards_of(ReportParticipant(dds, "Диспетчер", "dds", "DDS_01"), cards) == [system]
