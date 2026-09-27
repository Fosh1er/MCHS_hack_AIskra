"""Фабрика адаптеров по конфигу. Вызывается только из composition root."""

from __future__ import annotations

from aiskra.ai.adapters.caching import CachingLLM, CachingTTS
from aiskra.ai.adapters.fake import FakeLLM
from aiskra.ai.adapters.openai_compatible import OpenAICompatibleLLM
from aiskra.ai.adapters.speech import FakeSTT, FakeTTS
from aiskra.ai.config import AIConfig, ProviderConfig
from aiskra.ai.ports import LLMPort, STTPort, TTSPort
from aiskra.ai.router import ModelRouter, TaskProfile
from aiskra.shared.cache import CachePort


def build_llm(name: str, cfg: ProviderConfig) -> LLMPort:
    if cfg.kind == "fake":
        return FakeLLM(name=name, model=cfg.model)
    assert cfg.base_url  # гарантировано валидацией конфига
    return OpenAICompatibleLLM(
        name=name,
        base_url=cfg.base_url,
        model=cfg.model,
        api_key_env=cfg.api_key_env,
        timeout_s=cfg.timeout_s,
        max_concurrency=cfg.max_concurrency,
        structured_output=cfg.structured_output,
        extra_body=cfg.extra_body,
    )


def build_router(cfg: AIConfig, cache: CachePort) -> ModelRouter:
    clients: dict[str, LLMPort] = {name: CachingLLM(build_llm(name, p), cache) for name, p in cfg.providers.items()}
    profiles = {
        task: TaskProfile(
            task=task,
            provider=t.provider,
            temperature=t.temperature,
            max_tokens=t.max_tokens,
            timeout_s=t.timeout_s,
            cache_mode=t.cache,
            cache_ttl_s=t.cache_ttl,
            prompt_version=t.prompt_version,
        )
        for task, t in cfg.tasks.items()
    }
    return ModelRouter(profiles=profiles, clients=clients, default_provider=cfg.default_provider)


def build_tts(cfg: AIConfig, cache: CachePort) -> TTSPort:
    return CachingTTS(FakeTTS(), cache, ttl_s=cfg.tts.cache_ttl)


def build_stt(cfg: AIConfig) -> STTPort:
    return FakeSTT()
