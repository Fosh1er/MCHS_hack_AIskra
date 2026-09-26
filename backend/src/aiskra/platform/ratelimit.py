"""Ограничение неудачных входов с одного IP (п. 6.2): скользящее окно в памяти процесса (один процесс API,
ADR-0005). Успешный вход сбрасывает счётчик адреса."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

from aiskra.shared.errors import TooManyRequestsError


class SlidingWindowThrottle:
    def __init__(self, *, limit: int = 20, window_s: float = 900, clock: Callable[[], float] = time.monotonic) -> None:
        self._limit = limit
        self._window = window_s
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def _recent(self, key: str) -> deque[float]:
        q = self._hits.setdefault(key, deque())
        edge = self._clock() - self._window
        while q and q[0] < edge:
            q.popleft()
        return q

    def check(self, key: str) -> None:
        q = self._recent(key)
        if len(q) >= self._limit:
            wait = int(q[0] + self._window - self._clock()) + 1
            raise TooManyRequestsError(
                f"Слишком много неудачных попыток входа с этого адреса. Повторите через {wait // 60 + 1} мин."
            )

    def failed(self, key: str) -> None:
        self._recent(key).append(self._clock())
        if len(self._hits) > 10_000:  # защита памяти от перебора адресов
            for k in [k for k, v in self._hits.items() if not v][:5_000]:
                del self._hits[k]

    def succeeded(self, key: str) -> None:
        self._hits.pop(key, None)
