"""Адаптеры кеша для одного процесса (MVP)."""

from __future__ import annotations

import copy
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from aiskra.shared.cache.ports import CacheStats


class InMemoryTTLCache:
    """LRU-кеш с TTL на каждую запись. Не потокобезопасен — рассчитан на один event loop."""

    def __init__(self, *, max_items: int = 5000, clock: Callable[[], float] = time.monotonic) -> None:
        self._data: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self._max = max_items
        self._clock = clock
        self._stats = CacheStats()

    async def get(self, key: str) -> dict[str, Any] | None:
        item = self._data.get(key)
        if item is None:
            self._stats.misses += 1
            return None
        expires_at, value = item
        if expires_at <= self._clock():
            del self._data[key]
            self._stats.misses += 1
            return None
        self._data.move_to_end(key)
        self._stats.hits += 1
        return copy.deepcopy(value)  # защищаем закешированное значение от мутаций снаружи

    async def set(self, key: str, value: dict[str, Any], *, ttl_s: int) -> None:
        if ttl_s <= 0:
            return
        self._data[key] = (self._clock() + ttl_s, copy.deepcopy(value))
        self._data.move_to_end(key)
        self._stats.sets += 1
        while len(self._data) > self._max:
            self._data.popitem(last=False)

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def clear(self) -> None:
        self._data.clear()

    def stats(self) -> CacheStats:
        self._stats.size = len(self._data)
        return self._stats


class NullCache:
    """Кеш выключен: всегда промах. Используется при `ai.cache.backend: off`."""

    def __init__(self) -> None:
        self._stats = CacheStats()

    async def get(self, key: str) -> dict[str, Any] | None:
        self._stats.misses += 1
        return None

    async def set(self, key: str, value: dict[str, Any], *, ttl_s: int) -> None:
        return None

    async def delete(self, key: str) -> None:
        return None

    async def clear(self) -> None:
        return None

    def stats(self) -> CacheStats:
        return self._stats
