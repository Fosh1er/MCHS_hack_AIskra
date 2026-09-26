"""Команда: отправить пробный запрос модели, назначенной на ИИ-задачу.

Это команда, а не запрос: вызов модели — внешний побочный эффект (время, стоимость, запись в кеш).
"""

from __future__ import annotations

from dataclasses import dataclass

from aiskra.ai.ports import ChatMessage
from aiskra.ai.router import ModelRouter
from aiskra.ai.tasks import AITask
from aiskra.shared.application import Command
from aiskra.shared.errors import DomainError

MAX_PROMPT_LEN = 2000


@dataclass(frozen=True, kw_only=True)
class ProbeModel(Command):
    prompt: str
    task: str = AITask.PROBE


@dataclass(frozen=True)
class ProbeModelResult:
    task: str
    provider: str
    model: str
    text: str
    cached: bool
    latency_ms: int


class ProbeModelHandler:
    def __init__(self, router: ModelRouter) -> None:
        self._router = router

    async def __call__(self, cmd: ProbeModel) -> ProbeModelResult:
        prompt = cmd.prompt.strip()
        if not prompt:
            raise DomainError("Пустой запрос к модели", code="empty_prompt")
        if len(prompt) > MAX_PROMPT_LEN:
            raise DomainError(f"Запрос длиннее {MAX_PROMPT_LEN} символов", code="prompt_too_long")
        model = self._router.for_task(cmd.task)
        result = await model.complete(
            [
                ChatMessage("system", "Ты — диагностический ответчик тренажёра 112. Отвечай кратко по-русски."),
                ChatMessage("user", prompt),
            ]
        )
        return ProbeModelResult(
            task=cmd.task,
            provider=result.provider,
            model=result.model,
            text=result.text,
            cached=result.cached,
            latency_ms=result.latency_ms,
        )
