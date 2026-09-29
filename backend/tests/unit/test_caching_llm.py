import asyncio

import pytest
from pydantic import BaseModel

from aiskra.ai.adapters.caching import CachingLLM, CachingTTS
from aiskra.ai.adapters.fake import FakeLLM
from aiskra.ai.adapters.speech import FakeTTS
from aiskra.ai.ports import AudioBlob, CacheDirective, ChatMessage, LLMParams, LLMResult, VoiceProfile
from aiskra.shared.cache import InMemoryTTLCache
from aiskra.shared.errors import ExternalServiceError

MSG = [ChatMessage("user", "Какой адрес?")]


def params(**kw: object) -> LLMParams:
    base: dict[str, object] = {"task": "judge", "temperature": 0.0}
    base.update(kw)
    return LLMParams(**base)  # type: ignore[arg-type]


async def test_exact_repeat_is_served_from_cache() -> None:
    inner = FakeLLM()
    llm = CachingLLM(inner, InMemoryTTLCache())
    first = await llm.complete(MSG, params=params())
    second = await llm.complete(MSG, params=params())
    assert len(inner.calls) == 1
    assert not first.cached and second.cached
    assert second.text == first.text


async def test_nonzero_temperature_without_seed_bypasses_cache() -> None:
    inner = FakeLLM()
    llm = CachingLLM(inner, InMemoryTTLCache())
    await llm.complete(MSG, params=params(temperature=0.8))
    await llm.complete(MSG, params=params(temperature=0.8))
    assert len(inner.calls) == 2


async def test_prompt_version_change_invalidates() -> None:
    inner = FakeLLM()
    llm = CachingLLM(inner, InMemoryTTLCache())
    await llm.complete(MSG, params=params(prompt_version="v1"))
    await llm.complete(MSG, params=params(prompt_version="v2"))
    assert len(inner.calls) == 2


async def test_task_mode_groups_same_question_within_scope() -> None:
    inner = FakeLLM()
    llm = CachingLLM(inner, InMemoryTTLCache())
    p = params(task="applicant_actor", temperature=0.6, cache=CacheDirective(mode="task", scope="scn-1"))
    await llm.complete([ChatMessage("user", "Какой адрес?")], params=p)
    hit = await llm.complete([ChatMessage("user", "какой  адрес")], params=p)
    assert hit.cached and len(inner.calls) == 1
    other = params(task="applicant_actor", temperature=0.6, cache=CacheDirective(mode="task", scope="scn-2"))
    await llm.complete([ChatMessage("user", "Какой адрес?")], params=other)
    assert len(inner.calls) == 2


async def test_errors_are_not_cached() -> None:
    class Flaky(FakeLLM):
        fail = True

        async def complete(self, messages, *, params, schema=None) -> LLMResult:  # type: ignore[no-untyped-def]
            if self.fail:
                self.fail = False
                raise ExternalServiceError("down")
            return await super().complete(messages, params=params, schema=schema)

    llm = CachingLLM(Flaky(), InMemoryTTLCache())
    with pytest.raises(ExternalServiceError):
        await llm.complete(MSG, params=params())
    ok = await llm.complete(MSG, params=params())
    assert not ok.cached


async def test_single_flight_collapses_concurrent_identical_calls() -> None:
    class Slow(FakeLLM):
        async def complete(self, messages, *, params, schema=None) -> LLMResult:  # type: ignore[no-untyped-def]
            await asyncio.sleep(0.05)
            return await super().complete(messages, params=params, schema=schema)

    inner = Slow()
    llm = CachingLLM(inner, InMemoryTTLCache())
    results = await asyncio.gather(*(llm.complete(MSG, params=params()) for _ in range(5)))
    assert len(inner.calls) == 1
    assert sum(r.cached for r in results) == 4


async def test_schema_is_reparsed_on_cache_hit() -> None:
    class Verdict(BaseModel):
        ok: bool = True
        score: int = 7

    llm = CachingLLM(FakeLLM(), InMemoryTTLCache())
    await llm.complete(MSG, params=params(), schema=Verdict)
    hit = await llm.complete(MSG, params=params(), schema=Verdict)
    assert hit.cached and isinstance(hit.parsed, Verdict) and hit.parsed.score == 7


async def test_tts_cache() -> None:
    inner = FakeTTS()
    tts = CachingTTS(inner, max_bytes=1_000_000, ttl_s=60)
    a = await tts.synthesize("Бригада выехала", voice=VoiceProfile())
    b = await tts.synthesize("Бригада  выехала", voice=VoiceProfile())
    assert inner.calls == 1 and b.cached and a.content == b.content
    await tts.synthesize("Бригада выехала", voice=VoiceProfile(style="panicked"))  # другая подача — другой звук
    assert inner.calls == 2


class SlowTTS:
    """Синтез по 100 байт, с паузой — чтобы одновременные запросы встретились."""

    enabled = True
    model_id = "slow"

    def __init__(self) -> None:
        self.calls = 0

    async def synthesize(self, text: str, *, voice: VoiceProfile) -> AudioBlob:
        self.calls += 1
        await asyncio.sleep(0.01)
        return AudioBlob(content=b"x" * 100, mime="audio/wav")


async def test_tts_cache_bounded_by_bytes() -> None:
    """П. 3.6: аудио тяжёлое — лимит кеша в байтах, давно не звучавшее вытесняется."""
    inner = SlowTTS()
    tts = CachingTTS(inner, max_bytes=250, ttl_s=60)
    for phrase in ("один", "два", "три"):
        await tts.synthesize(phrase, voice=VoiceProfile())
    assert tts.size_bytes == 200 and inner.calls == 3  # «один» вытеснен
    assert (await tts.synthesize("три", voice=VoiceProfile())).cached
    assert not (await tts.synthesize("один", voice=VoiceProfile())).cached and inner.calls == 4


async def test_tts_cache_single_flight_and_ttl() -> None:
    inner = SlowTTS()
    now = [0.0]
    tts = CachingTTS(inner, max_bytes=10_000, ttl_s=60, clock=lambda: now[0])
    await asyncio.gather(*(tts.synthesize("Алло", voice=VoiceProfile()) for _ in range(3)))
    assert inner.calls == 1  # одновременные запросы одной реплики — один синтез
    now[0] = 61
    await tts.synthesize("Алло", voice=VoiceProfile())
    assert inner.calls == 2 and tts.size_bytes == 100  # просроченная запись заменена, не задвоена
