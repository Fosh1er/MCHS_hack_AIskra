"""Single-flight: одинаковые одновременные запросы ждут один результат, а не идут в модель N раз."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar, cast

T = TypeVar("T")


class SingleFlight:
    def __init__(self) -> None:
        self._inflight: dict[str, asyncio.Future[object]] = {}

    async def run(self, key: str, fn: Callable[[], Awaitable[T]]) -> tuple[T, bool]:
        """Выполнить fn один раз на ключ. Возвращает (результат, был_ли_это_попутный_вызов)."""
        existing = self._inflight.get(key)
        if existing is not None:
            return cast(T, await asyncio.shield(existing)), True
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[object] = loop.create_future()
        self._inflight[key] = fut
        try:
            result = await fn()
        except BaseException as exc:
            fut.set_exception(exc)
            fut.exception()  # помечаем исключение как полученное, чтобы не было предупреждения
            raise
        else:
            fut.set_result(result)
            return result, False
        finally:
            self._inflight.pop(key, None)
