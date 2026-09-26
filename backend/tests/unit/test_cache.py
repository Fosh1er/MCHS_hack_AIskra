from aiskra.shared.cache import InMemoryTTLCache, make_key, normalize_loose, normalize_strict


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


async def test_ttl_expiry() -> None:
    clock = FakeClock()
    cache = InMemoryTTLCache(clock=clock)
    await cache.set("k", {"v": 1}, ttl_s=10)
    assert await cache.get("k") == {"v": 1}
    clock.t = 11
    assert await cache.get("k") is None


async def test_lru_eviction_and_copy() -> None:
    cache = InMemoryTTLCache(max_items=2)
    await cache.set("a", {"v": 1}, ttl_s=60)
    await cache.set("b", {"v": 2}, ttl_s=60)
    await cache.get("a")  # a становится свежим
    await cache.set("c", {"v": 3}, ttl_s=60)
    assert await cache.get("b") is None
    got = await cache.get("a")
    assert got is not None
    got["v"] = 999
    assert await cache.get("a") == {"v": 1}, "кеш не должен мутировать снаружи"


def test_normalization_and_keys() -> None:
    assert normalize_loose("Какой  АДРЕС?!") == normalize_loose("какой адрес")
    assert normalize_loose("ещё") == "еще"
    assert normalize_strict("  a \n b ") == "a b"
    assert make_key("ns", 1, "x") == make_key("ns", 1, "x")
    assert make_key("ns", 1, "x") != make_key("ns", 1, "y")
