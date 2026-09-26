"""Детерминированная модель для тестов, офлайн-разработки и демо без модели.

Ответ зависит только от входа → тесты стабильны. Для структурированного вывода собирает
минимальный валидный объект по JSON Schema или берёт заготовку из `fixtures[task]`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel

from aiskra.ai.adapters.schema_tools import example_from_schema
from aiskra.ai.ports import ChatMessage, LLMParams, LLMResult

Fixture = Callable[[list[ChatMessage]], Any] | dict[str, Any] | str


class FakeLLM:
    def __init__(
        self, *, name: str = "fake", model: str = "fake-llm", fixtures: Mapping[str, Fixture] | None = None
    ) -> None:
        self._name = name
        self._model = model
        self._fixtures = dict(fixtures or {})
        self.calls: list[tuple[list[ChatMessage], LLMParams]] = []  # для проверок в тестах

    @property
    def provider_name(self) -> str:
        return self._name

    @property
    def model_id(self) -> str:
        return self._model

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        params: LLMParams,
        schema: type[BaseModel] | None = None,
    ) -> LLMResult:
        self.calls.append((messages, params))
        fixture = self._fixtures.get(params.task)
        payload: Any = fixture(messages) if callable(fixture) else fixture
        parsed = None
        if schema is not None:
            data = payload if isinstance(payload, dict) else example_from_schema(schema.model_json_schema())
            parsed = schema.model_validate(data)
            text = parsed.model_dump_json()
        elif isinstance(payload, str):
            text = payload
        else:
            last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
            text = f"[fake:{params.task}] {last_user[:120]}"
        return LLMResult(text=text, provider=self._name, model=self._model, latency_ms=0, parsed=parsed)

    async def aclose(self) -> None:
        return None
