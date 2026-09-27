"""Адаптер OpenAI-совместимого API (/v1/chat/completions).

Покрывает: Ollama, vLLM, llama.cpp server, LM Studio и внешние сервисы с OpenAI-протоколом.
Одна строка в config/ai.yaml переключает демо-API ↔ локальную модель (ответы #710, #746).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ValidationError

from aiskra.ai.adapters.schema_tools import extract_json
from aiskra.ai.ports import ChatMessage, LLMParams, LLMResult, LLMUsage
from aiskra.shared.errors import ExternalServiceError

StructuredMode = Literal["json_schema", "json_object", "prompt"]


class OpenAICompatibleLLM:
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        model: str,
        api_key_env: str | None = None,
        timeout_s: float = 60.0,
        max_concurrency: int = 4,
        structured_output: StructuredMode = "json_schema",
        extra_body: dict[str, Any] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers = {"Content-Type": "application/json"}
        api_key = os.environ.get(api_key_env, "") if api_key_env else ""
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._name = name
        self._model = model
        self._structured = structured_output
        self._extra = dict(extra_body or {})
        self._timeout = timeout_s
        # Ограничение параллельности: на CPU-сервере без GPU модель не должна «съедать» все ядра.
        self._sem = asyncio.Semaphore(max_concurrency)
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout_s, transport=transport
        )

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
        msgs = [{"role": m.role, "content": m.content} for m in messages]
        body: dict[str, Any] = {**self._extra, "model": self._model, "temperature": params.temperature}
        if params.max_tokens:
            body["max_tokens"] = params.max_tokens
        if params.seed is not None:
            body["seed"] = params.seed
        if schema is not None:
            self._apply_schema(body, msgs, schema)
        body["messages"] = msgs

        started = time.perf_counter()
        text, usage = await self._post(body, timeout_s=params.timeout_s)
        parsed = None
        if schema is not None:
            try:
                parsed = schema.model_validate(extract_json(text))
            except (ValueError, ValidationError) as first_error:
                # Одна попытка исправления: возвращаем модели её ответ и ошибку валидации.
                body["messages"] = [
                    *msgs,
                    {"role": "assistant", "content": text},
                    {
                        "role": "user",
                        "content": f"Ответ не соответствует JSON-схеме: {first_error}. Верни только исправленный JSON.",
                    },
                ]
                text, usage = await self._post(body, timeout_s=params.timeout_s)
                try:
                    parsed = schema.model_validate(extract_json(text))
                except (ValueError, ValidationError) as exc:
                    raise ExternalServiceError(f"{self._name}: ответ не соответствует схеме: {exc}") from exc

        return LLMResult(
            text=text,
            provider=self._name,
            model=self._model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            usage=usage,
            parsed=parsed,
        )

    def _apply_schema(self, body: dict[str, Any], msgs: list[dict[str, str]], schema: type[BaseModel]) -> None:
        json_schema = schema.model_json_schema()
        if self._structured == "json_schema":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "schema": json_schema},
            }
        elif self._structured == "json_object":
            body["response_format"] = {"type": "json_object"}
        # Во всех режимах подсказываем схему в промпте — это повышает долю валидных ответов у малых моделей.
        msgs.insert(
            0,
            {
                "role": "system",
                "content": "Отвечай строго JSON по схеме:\n" + json.dumps(json_schema, ensure_ascii=False),
            },
        )

    async def _post(self, body: dict[str, Any], *, timeout_s: float | None) -> tuple[str, LLMUsage]:
        async with self._sem:
            try:
                resp = await self._http.post("/chat/completions", json=body, timeout=timeout_s or self._timeout)
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ExternalServiceError(
                    f"{self._name}: модель недоступна ({exc.__class__.__name__}: {exc})"
                ) from exc
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            # шлюзы (OpenRouter) при сбое поставщика отвечают 200 с {"error": …} вместо choices
            reason = (data.get("error") or {}).get("message") if isinstance(data, dict) else None
            raise ExternalServiceError(
                f"{self._name}: неожиданный формат ответа" + (f" — {str(reason)[:200]}" if reason else "")
            ) from exc
        u = data.get("usage") or {}
        return text, LLMUsage(prompt_tokens=u.get("prompt_tokens"), completion_tokens=u.get("completion_tokens"))

    async def aclose(self) -> None:
        await self._http.aclose()
