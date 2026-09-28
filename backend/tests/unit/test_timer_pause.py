"""П. 5.3: общее правило паузы учебного таймера — несколько пауз, всего не больше 10 минут."""

from datetime import UTC, datetime, timedelta

import pytest

from aiskra.modules.incidents.domain.timer_pause import MAX_TIMER_PAUSE, end_pause, start_pause
from aiskra.shared.errors import DomainError

T0 = datetime(2026, 9, 28, 10, 0, tzinfo=UTC)
LIMIT = int(MAX_TIMER_PAUSE.total_seconds() * 1000)


def test_pauses_add_up_to_limit() -> None:
    started = start_pause(None, None, T0)
    ms = end_pause(None, started, T0 + timedelta(seconds=40))
    assert ms == 40_000
    started = start_pause(ms, None, T0 + timedelta(seconds=60))
    assert end_pause(ms, started, T0 + timedelta(seconds=80)) == 60_000
    assert end_pause(ms, start_pause(ms, None, T0), T0 + timedelta(hours=1)) == LIMIT


def test_repeat_and_exhausted() -> None:
    assert start_pause(None, T0, T0 + timedelta(seconds=5)) == T0  # уже на паузе
    assert end_pause(1_000, None, T0) == 1_000  # паузы нет
    with pytest.raises(DomainError):
        start_pause(LIMIT, None, T0)
