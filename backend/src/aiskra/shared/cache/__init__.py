"""Кеш (ADR-0006): порт CachePort, адаптеры и построение ключей."""

from aiskra.shared.cache.keys import make_key, normalize_loose, normalize_strict
from aiskra.shared.cache.memory import InMemoryTTLCache, NullCache
from aiskra.shared.cache.ports import CachePort, CacheStats
from aiskra.shared.cache.singleflight import SingleFlight

__all__ = [
    "CachePort",
    "CacheStats",
    "InMemoryTTLCache",
    "NullCache",
    "SingleFlight",
    "make_key",
    "normalize_loose",
    "normalize_strict",
]
