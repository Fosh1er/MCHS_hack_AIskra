"""Маршрутизация ИИ-задач: задача → (клиент модели, параметры, политика кеша) по конфигу.

Код сценариев использования делает `router.for_task(AITask.JUDGE).complete(...)` и не знает,
какая модель и какой провайдер под ним. Смена модели — правка config/ai.yaml.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import BaseModel

from aiskra.ai.ports import CacheDirective, CacheMode, ChatMessage, LLMParams, LLMPort, LLMResult


@dataclass(frozen=True)
class TaskProfile:
    """Профиль задачи. Для задач без явной настройки в config/ai.yaml — детерминированный режим
    (temperature 0): одинаковый вход даёт одинаковый ответ и попадает в кеш."""

    task: str
    provider: str
    temperature: float = 0.0
    max_tokens: int | None = None
    timeout_s: float | None = None
    cache_mode: CacheMode = "exact"
    cache_ttl_s: int = 86_400
    prompt_version: str = "v1"


class TaskModel:
    """Модель, привязанная к задаче: параметры и кеш уже подставлены."""

    def __init__(self, profile: TaskProfile, client: LLMPort) -> None:
        self.profile = profile
        self._client = client

    @property
    def provider_name(self) -> str:
        return self._client.provider_name

    @property
    def model_id(self) -> str:
        return self._client.model_id

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        schema: type[BaseModel] | None = None,
        cache_scope: str | None = None,
        seed: int | None = None,
    ) -> LLMResult:
        p = self.profile
        params = LLMParams(
            task=p.task,
            temperature=p.temperature,
            max_tokens=p.max_tokens,
            timeout_s=p.timeout_s,
            seed=seed,
            prompt_version=p.prompt_version,
            cache=CacheDirective(mode=p.cache_mode, ttl_s=p.cache_ttl_s, scope=cache_scope),
        )
        return await self._client.complete(messages, params=params, schema=schema)


@dataclass(frozen=True)
class TaskInfo:
    task: str
    provider: str
    model: str
    temperature: float
    cache_mode: CacheMode
    cache_ttl_s: int


class ModelRouter:
    def __init__(
        self,
        *,
        profiles: Mapping[str, TaskProfile],
        clients: Mapping[str, LLMPort],
        default_provider: str,
    ) -> None:
        missing = {p.provider for p in profiles.values()} - set(clients)
        if missing or default_provider not in clients:
            raise ValueError(f"Нет клиентов для провайдеров: {sorted(missing | {default_provider} - set(clients))}")
        self._profiles = dict(profiles)
        self._clients = dict(clients)
        self._default = default_provider

    def for_task(self, task: str) -> TaskModel:
        profile = self._profiles.get(task) or TaskProfile(task=task, provider=self._default)
        return TaskModel(profile, self._clients[profile.provider])

    def describe(self) -> list[TaskInfo]:
        return [
            TaskInfo(
                task=p.task,
                provider=p.provider,
                model=self._clients[p.provider].model_id,
                temperature=p.temperature,
                cache_mode=p.cache_mode,
                cache_ttl_s=p.cache_ttl_s,
            )
            for p in self._profiles.values()
        ]

    async def aclose(self) -> None:
        for client in self._clients.values():
            await client.aclose()
