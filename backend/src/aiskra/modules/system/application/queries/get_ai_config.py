"""Запрос: какие модели назначены на ИИ-задачи (без секретов). Только чтение."""

from __future__ import annotations

from dataclasses import dataclass

from aiskra.ai.router import ModelRouter, TaskInfo
from aiskra.shared.application import Query


@dataclass(frozen=True, kw_only=True)
class GetAIConfig(Query):
    pass


@dataclass(frozen=True)
class AIConfigView:
    allow_external: bool
    default_provider: str
    tasks: list[TaskInfo]


class GetAIConfigHandler:
    def __init__(self, router: ModelRouter, *, allow_external: bool, default_provider: str) -> None:
        self._router = router
        self._allow_external = allow_external
        self._default = default_provider

    async def __call__(self, query: GetAIConfig) -> AIConfigView:
        return AIConfigView(
            allow_external=self._allow_external, default_provider=self._default, tasks=self._router.describe()
        )
