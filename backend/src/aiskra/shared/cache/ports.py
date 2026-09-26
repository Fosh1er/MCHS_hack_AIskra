"""Порт кеша. Значения — JSON-совместимые структуры: так адаптер можно заменить
на PostgreSQL/Redis без изменения вызывающего кода."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    sets: int = 0
    size: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


class CachePort(Protocol):
    async def get(self, key: str) -> dict[str, Any] | None: ...

    async def set(self, key: str, value: dict[str, Any], *, ttl_s: int) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def clear(self) -> None: ...

    def stats(self) -> CacheStats: ...
