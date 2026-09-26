"""Кеширующие декораторы над портами ИИ (ADR-0006).

CachingLLM реализует тот же LLMPort и оборачивает любой адаптер — сценарии использования
о кеше не знают. Правила:
- temperature > 0 без seed в режиме exact → не кешируем (сохраняем разнообразие генерации);
- ошибки и невалидный вывод не кешируются (исключение пролетает мимо кеша);
- смена модели или версии промпта автоматически даёт новые ключи;
- одинаковые одновременные запросы схлопываются (single-flight).
"""

from __future__ import annotations

import base64
import time

from pydantic import BaseModel

from aiskra.ai.ports import (
    AudioBlob,
    ChatMessage,
    LLMParams,
    LLMPort,
    LLMResult,
    LLMUsage,
    TTSPort,
    VoiceProfile,
)
from aiskra.shared.cache import CachePort, SingleFlight, make_key, normalize_loose, normalize_strict


def cache_key(model: str, messages: list[ChatMessage], params: LLMParams, schema: type[BaseModel] | None) -> str | None:
    """Ключ кеша или None, если вызов кешировать нельзя."""
    c = params.cache
    if c.mode == "off":
        return None
    schema_name = schema.__name__ if schema else None
    if c.mode == "task":
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return make_key(
            "llm:task", model, params.task, params.prompt_version, c.scope, normalize_loose(last_user), schema_name
        )
    if params.temperature > 0 and params.seed is None:
        return None
    return make_key(
        "llm:exact",
        model,
        params.task,
        params.prompt_version,
        params.temperature,
        params.seed,
        params.max_tokens,
        [(m.role, normalize_strict(m.content)) for m in messages],
        schema_name,
    )


class CachingLLM:
    def __init__(self, inner: LLMPort, cache: CachePort) -> None:
        self._inner = inner
        self._cache = cache
        self._flight = SingleFlight()

    @property
    def provider_name(self) -> str:
        return self._inner.provider_name

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        params: LLMParams,
        schema: type[BaseModel] | None = None,
    ) -> LLMResult:
        key = cache_key(self._inner.model_id, messages, params, schema)
        if key is None:
            return await self._inner.complete(messages, params=params, schema=schema)

        started = time.perf_counter()
        hit = await self._cache.get(key)
        if hit is not None:
            return self._from_cache(hit, schema, started)

        async def call() -> LLMResult:
            result = await self._inner.complete(messages, params=params, schema=schema)
            await self._cache.set(key, self._to_cache(result), ttl_s=params.cache.ttl_s)
            return result

        result, joined = await self._flight.run(key, call)
        if joined:  # дождались чужой вызов — для этого запроса это попадание в кеш
            return LLMResult(
                text=result.text,
                provider=result.provider,
                model=result.model,
                latency_ms=int((time.perf_counter() - started) * 1000),
                cached=True,
                usage=result.usage,
                parsed=result.parsed,
            )
        return result

    @staticmethod
    def _to_cache(r: LLMResult) -> dict[str, object]:
        return {
            "text": r.text,
            "provider": r.provider,
            "model": r.model,
            "prompt_tokens": r.usage.prompt_tokens,
            "completion_tokens": r.usage.completion_tokens,
        }

    @staticmethod
    def _from_cache(hit: dict[str, object], schema: type[BaseModel] | None, started: float) -> LLMResult:
        text = str(hit["text"])
        parsed = schema.model_validate_json(text) if schema is not None else None
        pt, ct = hit.get("prompt_tokens"), hit.get("completion_tokens")
        return LLMResult(
            text=text,
            provider=str(hit["provider"]),
            model=str(hit["model"]),
            latency_ms=int((time.perf_counter() - started) * 1000),
            cached=True,
            usage=LLMUsage(
                prompt_tokens=pt if isinstance(pt, int) else None, completion_tokens=ct if isinstance(ct, int) else None
            ),
            parsed=parsed,
        )

    async def aclose(self) -> None:
        await self._inner.aclose()


class CachingTTS:
    """Синтез речи — самая дорогая операция на CPU: одинаковая фраза тем же голосом синтезируется один раз."""

    def __init__(self, inner: TTSPort, cache: CachePort, *, ttl_s: int) -> None:
        self._inner = inner
        self._cache = cache
        self._ttl = ttl_s

    async def synthesize(self, text: str, *, voice: VoiceProfile) -> AudioBlob:
        key = make_key("tts", normalize_strict(text), voice.voice, voice.speed, voice.emotion)
        hit = await self._cache.get(key)
        if hit is not None:
            return AudioBlob(content=base64.b64decode(str(hit["b64"])), mime=str(hit["mime"]), cached=True)
        blob = await self._inner.synthesize(text, voice=voice)
        await self._cache.set(key, {"b64": base64.b64encode(blob.content).decode(), "mime": blob.mime}, ttl_s=self._ttl)
        return blob
