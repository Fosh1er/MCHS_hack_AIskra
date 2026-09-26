"""П. 6.2: скользящее окно неудачных входов."""

import pytest

from aiskra.platform.ratelimit import SlidingWindowThrottle
from aiskra.shared.errors import TooManyRequestsError


def test_window_slides_and_resets() -> None:
    now = [0.0]
    t = SlidingWindowThrottle(limit=3, window_s=60, clock=lambda: now[0])
    for _ in range(3):
        t.check("1.2.3.4")
        t.failed("1.2.3.4")
    with pytest.raises(TooManyRequestsError):
        t.check("1.2.3.4")
    t.check("5.6.7.8")  # другой адрес не затронут
    now[0] = 61
    t.check("1.2.3.4")  # окно прошло
    t.failed("1.2.3.4")
    t.succeeded("1.2.3.4")
    for _ in range(3):
        t.check("1.2.3.4")
        t.failed("1.2.3.4")
