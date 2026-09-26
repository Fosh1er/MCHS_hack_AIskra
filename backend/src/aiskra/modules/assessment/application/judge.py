"""ИИ-судья (п. 3.4, задача `judge`): смысл описания, регламентность комментариев, грамотность.
Без модели (fake) или при ошибке — None: критерии помечаются «не проверено» и в итог не входят."""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field

from aiskra.ai.ports import ChatMessage
from aiskra.ai.prompts import load_prompt
from aiskra.ai.router import ModelRouter
from aiskra.ai.tasks import AITask
from aiskra.shared.errors import ExternalServiceError

log = logging.getLogger(__name__)


class JudgeRemark(BaseModel):
    quote: str = Field(max_length=200)
    fix: str = Field(max_length=200)


class JudgeOut(BaseModel):
    meaning: float | None = Field(default=None, ge=0, le=1)
    regulation: float | None = Field(default=None, ge=0, le=1)
    grammar: float | None = Field(default=None, ge=0, le=1)
    errors: list[JudgeRemark] = Field(default_factory=list, max_length=5)


class Judge:
    def __init__(self, router: ModelRouter) -> None:
        self._router = router

    async def check(self, *, legend: str, description: str, comments: list[str]) -> JudgeOut | None:
        model = self._router.for_task(AITask.JUDGE)
        if model.provider_name == "fake":
            return None
        payload = {"легенда_заявителя": legend, "описание_оператора": description, "комментарии_к_статусам": comments}
        try:
            result = await model.complete(
                [
                    ChatMessage(role="system", content=load_prompt(AITask.JUDGE)),
                    ChatMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
                ],
                schema=JudgeOut,
            )
            return result.parsed if isinstance(result.parsed, JudgeOut) else JudgeOut.model_validate_json(result.text)
        except (ExternalServiceError, ValueError) as e:
            log.warning("ИИ-судья недоступен: %s", e)
            return None
