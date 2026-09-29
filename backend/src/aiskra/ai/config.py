"""Конфигурация ИИ-слоя (config/ai.yaml) и защита изолированного контура.

- `${VAR}` / `${VAR:-default}` в YAML подставляются из окружения — ключи и адреса не хранятся в git.
- `allow_external: false` (по умолчанию) запрещает адреса моделей вне локального контура:
  разрешены localhost, частные сети (10/8, 172.16/12, 192.168/16) и однословные имена сервисов
  docker compose (`llm`, `ollama`). Требование ТЗ: работа без внешних сетей; ответ #746.
"""

from __future__ import annotations

import ipaddress
import os
import re
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from aiskra.ai.ports import CacheMode
from aiskra.shared.errors import ConfigError

_ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")
_DURATION_RE = re.compile(r"^(\d+)\s*([smhd])$")
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _yaml_bool_to_mode(value: object, on: str) -> object:
    """YAML 1.1 читает `off`/`on` как булевы значения — возвращаем им строковый смысл."""
    if value is False:
        return "off"
    if value is True:
        return on
    return value


def parse_duration(value: int | str) -> int:
    """`30` → 30 c; `15m` → 900; `7d` → 604800."""
    if isinstance(value, int):
        return value
    m = _DURATION_RE.match(value.strip())
    if not m:
        raise ValueError(f"Некорректная длительность: {value!r} (ожидается 30s / 15m / 12h / 7d)")
    return int(m.group(1)) * _UNITS[m.group(2)]


class ProviderConfig(BaseModel):
    kind: Literal["openai_compatible", "fake"]
    base_url: str | None = None
    api_key_env: str | None = None
    model: str = "fake-llm"
    timeout_s: float = 60.0
    max_concurrency: int = Field(default=4, ge=1)
    structured_output: Literal["json_schema", "json_object", "prompt"] = "json_schema"
    # дополнительные поля запроса провайдера, например OpenRouter: {reasoning: {enabled: false}} —
    # «рассуждающая» модель отвечает сразу, без хода рассуждений
    extra_body: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> ProviderConfig:
        if self.kind == "openai_compatible" and not self.base_url:
            raise ValueError("для openai_compatible обязателен base_url")
        return self


class TaskConfig(BaseModel):
    provider: str
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int | None = None
    timeout_s: float | None = None
    cache: CacheMode = "exact"
    cache_ttl: int = 86_400
    prompt_version: str = "v1"

    @field_validator("cache_ttl", mode="before")
    @classmethod
    def _ttl(cls, v: int | str) -> int:
        return parse_duration(v)

    @field_validator("cache", mode="before")
    @classmethod
    def _cache_mode(cls, v: object) -> object:
        return _yaml_bool_to_mode(v, on="exact")


class CacheConfig(BaseModel):
    backend: Literal["memory", "off"] = "memory"
    max_items: int = Field(default=5000, ge=1)

    @field_validator("backend", mode="before")
    @classmethod
    def _backend(cls, v: object) -> object:
        return _yaml_bool_to_mode(v, on="memory")


class SpeechConfig(BaseModel):
    """Речь: `fake` — выключено; `openai_compatible` — сервер с OpenAI-совместимым `/audio/transcriptions`
    (локальный Whisper: Speaches, faster-whisper; внешний: OpenRouter, OpenAI)."""

    kind: Literal["fake", "openai_compatible"] = "fake"
    base_url: str | None = None
    api_key_env: str | None = None
    model: str = "whisper-1"
    language: str = "ru"
    timeout_s: float = 30.0
    cache_ttl: int = 30 * 86_400

    @model_validator(mode="after")
    def _check_url(self) -> SpeechConfig:
        if self.kind == "openai_compatible" and not self.base_url:
            raise ValueError("для openai_compatible обязателен base_url")
        return self

    @field_validator("cache_ttl", mode="before")
    @classmethod
    def _ttl(cls, v: int | str) -> int:
        return parse_duration(v)


class TTSConfig(SpeechConfig):
    """Синтез речи собеседника (п. 3.6): сервер с OpenAI-совместимым `/audio/speech` — OpenRouter (Gemini,
    OpenAI TTS) на демо или Speaches с Piper в изолированном контуре.

    - `voices` — роль голоса → имя голоса провайдера: `applicant_female`, `applicant_male`, `brigade`, `service`,
      `operator` (реплики оператора в записи звонка, п. 8.7); роли без имени (или с пустым) получают `voice`;
    - `style` — как передать эмоцию: `google` (`speech_metadata.style`), `openai` (`instructions`) — параметрами
      провайдера через OpenRouter; `none` — только темп (`speed`), для Piper и других моделей без инструкций;
    - `response_format: pcm` — сырой звук (Gemini на OpenRouter), сервер оборачивает его в WAV с `pcm_rate`;
    - `cache_mb` — лимит кеша аудио в памяти процесса.
    """

    model: str = "tts-1"
    voice: str = ""
    voices: dict[str, str] = Field(default_factory=dict)
    style: Literal["google", "openai", "none"] = "none"
    response_format: Literal["mp3", "wav", "pcm"] = "mp3"
    pcm_rate: int = Field(default=24_000, ge=8_000, le=48_000)
    cache_mb: int = Field(default=64, ge=0)
    max_concurrency: int = Field(default=2, ge=1)
    timeout_s: float = 20.0


class AIConfig(BaseModel):
    allow_external: bool = False
    default_provider: str = "fake"
    providers: dict[str, ProviderConfig] = Field(default_factory=lambda: {"fake": ProviderConfig(kind="fake")})
    tasks: dict[str, TaskConfig] = Field(default_factory=dict)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    stt: SpeechConfig = Field(default_factory=SpeechConfig)

    @model_validator(mode="after")
    def _check_refs(self) -> AIConfig:
        names = set(self.providers)
        if self.default_provider not in names:
            raise ValueError(f"default_provider «{self.default_provider}» не описан в providers")
        for task, cfg in self.tasks.items():
            if cfg.provider not in names:
                raise ValueError(f"задача «{task}» ссылается на неизвестный провайдер «{cfg.provider}»")
        if not self.allow_external:
            # Проверяем только используемые провайдеры: объявленный, но не назначенный никуда — не вызывается.
            used = {self.default_provider, *(t.provider for t in self.tasks.values())}
            for name, p in self.providers.items():
                if name in used and p.base_url and not is_internal_url(p.base_url):
                    raise ValueError(
                        f"провайдер «{name}»: внешний адрес {p.base_url} запрещён (allow_external: false). "
                        "Для демо на внешнем API явно включите allow_external."
                    )
            for name, sp in (("stt", self.stt), ("tts", self.tts)):
                if sp.kind != "fake" and sp.base_url and not is_internal_url(sp.base_url):
                    raise ValueError(f"{name}: внешний адрес {sp.base_url} запрещён (allow_external: false)")
        return self


def is_internal_url(url: str) -> bool:
    host = urlparse(url).hostname or ""
    if host in {"localhost", "host.docker.internal"} or "." not in host:
        return True  # localhost или имя сервиса docker compose
    if host.endswith((".local", ".internal", ".lan")):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback


def _interpolate(value: Any) -> Any:
    if isinstance(value, str):
        return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), value)
    if isinstance(value, dict):
        return {k: _interpolate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(v) for v in value]
    return value


def load_ai_config(path: str | Path | None) -> AIConfig:
    """Загрузить конфиг. Нет файла → безопасный офлайн-режим с fake-моделью."""
    if path is None or not Path(path).exists():
        return AIConfig()
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    data = raw.get("ai", raw)
    try:
        return AIConfig.model_validate(_interpolate(data))
    except ValueError as exc:
        raise ConfigError(f"Некорректный {path}: {exc}") from exc
