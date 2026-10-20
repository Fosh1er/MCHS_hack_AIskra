"""ТЗ 6.1: удержание звонка в софтфоне — состояние, длительность, запрет реплик на удержании."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from aiskra.modules.training.domain.call import Call, CallParty, CallStatus
from aiskra.shared.errors import DomainError

T0 = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def _call() -> Call:
    c = Call(student_id=uuid4(), role="112", party=CallParty.APPLICANT, direction="in", started_at=T0)
    c.answer(T0)
    return c


def test_hold_and_resume_count_time() -> None:
    c = _call()
    assert c.hold(T0 + timedelta(seconds=5))
    assert c.status is CallStatus.HELD
    assert not c.hold(T0 + timedelta(seconds=6))  # повтор запроса — без изменений
    with pytest.raises(DomainError) as e:
        c.ensure_active()
    assert e.value.code == "call_held"
    assert c.resume(T0 + timedelta(seconds=25)) == 20
    assert c.status is CallStatus.ACTIVE and c.held_ms == 20_000 and c.held_at is None
    assert c.resume(T0 + timedelta(seconds=26)) == 0  # уже снят
    c.ensure_active()


def test_end_while_held_keeps_hold_time() -> None:
    c = _call()
    c.hold(T0)
    c.end(T0 + timedelta(seconds=7))
    assert c.status is CallStatus.ENDED and c.held_ms == 7_000
    with pytest.raises(DomainError):
        c.resume(T0 + timedelta(seconds=8))


def test_hold_only_during_conversation() -> None:
    c = Call(student_id=uuid4(), role="112", party=CallParty.APPLICANT, direction="in", started_at=T0)
    with pytest.raises(DomainError) as e:
        c.hold(T0)  # ещё звонит
    assert e.value.code == "call_not_active"
