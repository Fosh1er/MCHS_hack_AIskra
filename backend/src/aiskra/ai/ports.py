"""Порты ИИ. Любая модель (внешний API, Ollama, vLLM, llama.cpp, fake) — адаптер к этим протоколам."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import BaseModel

Role = Literal["system", "user", "assistant"]
CacheMode = Literal["off", "exact", "task"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class CacheDirective:
    """Как кешировать вызов (ADR-0006).

    - off   — не кешировать;
    - exact — ключ по всему запросу (модель, промпт, сообщения, параметры);
    - task  — ключ по заданию: scope (например, id сценария + раскрытые факты) + нормализованный
              последний вопрос пользователя. Одинаковый вопрос по одному сценарию → один ответ модели.
    """

    mode: CacheMode = "exact"
    ttl_s: int = 86_400
    scope: str | None = None


@dataclass(frozen=True)
class LLMParams:
    task: str
    temperature: float = 0.2
    max_tokens: int | None = None
    timeout_s: float | None = None
    seed: int | None = None
    prompt_version: str = "v1"
    cache: CacheDirective = field(default_factory=CacheDirective)


@dataclass(frozen=True)
class LLMUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass(frozen=True)
class LLMResult:
    text: str
    provider: str
    model: str
    latency_ms: int
    cached: bool = False
    usage: LLMUsage = field(default_factory=LLMUsage)
    parsed: BaseModel | None = None


class LLMPort(Protocol):
    """Языковая модель. При ошибке провайдера адаптер поднимает ExternalServiceError."""

    @property
    def provider_name(self) -> str: ...

    @property
    def model_id(self) -> str: ...

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        params: LLMParams,
        schema: type[BaseModel] | None = None,
    ) -> LLMResult: ...

    async def aclose(self) -> None: ...


@dataclass(frozen=True)
class VoiceProfile:
    voice: str = "default"
    speed: float = 1.0
    emotion: str | None = None


@dataclass(frozen=True)
class AudioBlob:
    content: bytes
    mime: str = "audio/wav"
    cached: bool = False


@dataclass(frozen=True)
class Transcript:
    text: str
    confidence: float | None = None


class TTSPort(Protocol):
    async def synthesize(self, text: str, *, voice: VoiceProfile) -> AudioBlob: ...


class STTPort(Protocol):
    async def transcribe(self, audio: bytes, *, lang: str = "ru") -> Transcript: ...
