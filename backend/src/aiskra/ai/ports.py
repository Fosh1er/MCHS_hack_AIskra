"""Порты ИИ. Любая модель (внешний API, Ollama, vLLM, llama.cpp, fake) — адаптер к этим протоколам."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

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


@runtime_checkable
class LLMStreamPort(Protocol):
    """Модель, которая умеет отдавать ответ по мере генерации (F1, ADR-0013). Необязательное расширение `LLMPort`:
    адаптер без него отвечает целиком, а `TaskModel.stream` отдаёт этот ответ одним куском."""

    def stream(self, messages: list[ChatMessage], *, params: LLMParams) -> AsyncIterator[str]: ...


@dataclass(frozen=True)
class VoiceProfile:
    """Как озвучить реплику. `voice` — роль голоса («applicant_female», «brigade»…): имя голоса провайдера
    подставляет адаптер по конфигу. `style` — подача словами («panicked, very fast…») — адаптер передаёт её
    параметром провайдера, а не текстом реплики (п. 3.6, ADR-0011).

    F3: `sounds` — неречевые звуки реплики (sob, gasp, pant, sigh, cough…), `agitation` — насколько взволнованно
    звучать, 0–3. Как их передать модели, решает адаптер: Gemini — теги в тексте, движку без стиля — пунктуация.
    Текст реплики в звонке от этого не меняется."""

    voice: str = "default"
    speed: float = 1.0
    emotion: str | None = None
    style: str | None = None
    sounds: tuple[str, ...] = ()
    agitation: int = 0


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
    """Синтез речи. При ошибке провайдера адаптер поднимает ExternalServiceError."""

    @property
    def enabled(self) -> bool:
        """False — серверный синтез не настроен: реплики озвучивает браузер."""
        ...

    @property
    def model_id(self) -> str: ...

    async def synthesize(self, text: str, *, voice: VoiceProfile) -> AudioBlob: ...


class STTPort(Protocol):
    @property
    def enabled(self) -> bool:
        """False — распознавание не настроено (офлайн-заглушка): интерфейс не показывает микрофон."""
        ...

    async def transcribe(self, audio: bytes, *, lang: str = "ru", mime: str = "audio/webm") -> Transcript: ...
