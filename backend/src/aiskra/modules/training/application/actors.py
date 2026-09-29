"""Ролевые агенты (п. 3.3) поверх ModelRouter: с моделью — промпт из aiskra/ai/prompts, без модели (fake) —
детерминированный офлайн-режим `domain/actors.py`. Модель ошибается или недоступна — тоже офлайн-ответ:
занятие не должно вставать из-за сети."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from aiskra.ai.ports import ChatMessage
from aiskra.ai.prompts import load_prompt
from aiskra.ai.router import ModelRouter
from aiskra.ai.tasks import AITask
from aiskra.modules.training.application.ports.scenarios import DdsCallContext
from aiskra.modules.training.domain.actors import applicant_reply, brigade_reply, service_reply
from aiskra.modules.training.domain.call import CallMessage, Speaker
from aiskra.shared.errors import ExternalServiceError

log = logging.getLogger(__name__)
FAKE = "fake"
HISTORY = 12  # последних реплик в контексте модели
TOPIC_NAMES = {
    "what": "что случилось",
    "address": "адрес",
    "floor": "подъезд, этаж, квартира",
    "name": "своё имя",
    "phone": "номер телефона",
    "victims": "есть ли пострадавшие",
    "danger": "угроза, распространение",
    "access": "доступ, дверь",
    "gas": "газ",
    "status": "кем приходишься пострадавшему",
}
INTENSITY_NOTES = {
    1: "сдержанно: без мата, крика на полной громкости и натуралистичных подробностей",
    2: "обычно",
    3: "ярко, но без мата и натуралистичных подробностей травм",
}


def _topics(topics: list[str]) -> str:
    return ", ".join(TOPIC_NAMES.get(t, t) for t in topics)


class ActOut(BaseModel):
    code: str = Field(max_length=32)
    quote: str = Field(default="", max_length=200)


class PsyActsOut(BaseModel):
    acts: list[ActOut] = Field(default_factory=list, max_length=20)


@dataclass(frozen=True)
class PsyPrompt:
    """Что модель знает о состоянии заявителя на этом ходе (п. 3.6). Эталон сюда не попадает."""

    profile_title: str
    level: int
    level_title: str
    speech: str
    rules: str
    intensity: int
    allowed: list[str]
    blocked: list[str]


def _history(messages: list[CallMessage]) -> list[ChatMessage]:
    out: list[ChatMessage] = []
    for m in messages[-HISTORY:]:
        if m.speaker is Speaker.OPERATOR:
            out.append(ChatMessage(role="user", content=m.text))
        elif m.speaker is Speaker.PARTY:
            out.append(ChatMessage(role="assistant", content=m.text))
    return out


class Actors:
    def __init__(self, router: ModelRouter) -> None:
        self._router = router

    def _online(self, task: AITask) -> bool:
        return self._router.for_task(task).provider_name != FAKE

    async def _ask(
        self, task: AITask, system: str, history: list[CallMessage], question: str, scope: str
    ) -> str | None:
        try:
            model = self._router.for_task(task)
            result = await model.complete(
                [
                    ChatMessage(role="system", content=system),
                    *_history(history),
                    ChatMessage(role="user", content=question),
                ],
                cache_scope=scope,
            )
            text = result.text.strip()
            return text or None
        except ExternalServiceError as e:  # модель недоступна — офлайн-ответ
            log.warning("ИИ-задача %s недоступна: %s", task, e)
            return None

    async def applicant(
        self, legend: dict[str, Any], history: list[CallMessage], question: str, revealed: list[str], scope: str
    ) -> tuple[str, list[str]]:
        offline = applicant_reply(legend, question, revealed)
        if self._online(AITask.APPLICANT_ACTOR):
            public = {
                k: legend[k] for k in ("applicant", "address", "what", "details", "facts", "victims") if k in legend
            }
            system = load_prompt(AITask.APPLICANT_ACTOR).format(
                legend=json.dumps(public, ensure_ascii=False, indent=1), emotion=legend.get("emotion", "спокойно")
            )
            text = await self._ask(
                AITask.APPLICANT_ACTOR, system, history, question, f"{scope}:{','.join(offline.revealed)}"
            )
            if text:
                return text, offline.revealed
        return offline.text, offline.revealed

    async def applicant_psy(
        self, legend: dict[str, Any], history: list[CallMessage], question: str, psy: PsyPrompt, scope: str
    ) -> str | None:
        """Реплика заявителя с психологическим профилем (промпт applicant_actor/v2). None — модели нет или ошибка:
        вызывающий берёт офлайн-реплику профиля."""
        if not self._online(AITask.APPLICANT_ACTOR):
            return None
        public = {k: legend[k] for k in ("applicant", "address", "what", "details", "facts", "victims") if k in legend}
        system = (
            load_prompt(AITask.APPLICANT_ACTOR, "v2")
            .replace("{legend}", json.dumps(public, ensure_ascii=False, indent=1))
            .replace("{profile_title}", psy.profile_title)
            .replace("{level}", str(psy.level))
            .replace("{level_title}", psy.level_title)
            .replace("{speech}", psy.speech)
            .replace("{rules}", psy.rules)
            .replace("{intensity_note}", INTENSITY_NOTES.get(psy.intensity, "обычно"))
            .replace(
                "{allowed_topics}", ", ".join(TOPIC_NAMES.get(t, t) for t in psy.allowed) or "только что случилось"
            )
            .replace("{blocked_topics}", ", ".join(TOPIC_NAMES.get(t, t) for t in psy.blocked) or "—")
        )
        return await self._ask(AITask.APPLICANT_ACTOR, system, history, question, scope)

    async def classify_acts(self, question: str, context: str) -> list[tuple[str, str]] | None:
        """Разметка реплики оператора моделью (ИИ-задача PSY_ACTS). None — модели нет или ошибка."""
        if not self._online(AITask.PSY_ACTS):
            return None
        system = load_prompt(AITask.PSY_ACTS).replace("{context}", context)
        try:
            result = await self._router.for_task(AITask.PSY_ACTS).complete(
                [ChatMessage(role="system", content=system), ChatMessage(role="user", content=question)],
                schema=PsyActsOut,
            )
            out = (
                result.parsed if isinstance(result.parsed, PsyActsOut) else PsyActsOut.model_validate_json(result.text)
            )
        except (ExternalServiceError, ValueError) as e:
            log.warning("ИИ-задача psy_acts недоступна: %s", e)
            return None
        return [(a.code, a.quote) for a in out.acts]

    async def brigade(self, ctx: DdsCallContext, service_short: str, history: list[CallMessage], question: str) -> str:
        data = {
            "service_status": ctx.service_status,
            "order_no": ctx.order_no,
            "address": ctx.address,
            "victims": ctx.victims,
        }
        if self._online(AITask.BRIGADE_ACTOR):
            context = json.dumps({**data, "описание": ctx.description}, ensure_ascii=False)
            system = load_prompt(AITask.BRIGADE_ACTOR).format(
                service=service_short, context=context, status=ctx.service_status
            )
            text = await self._ask(
                AITask.BRIGADE_ACTOR, system, history, question, f"{ctx.card_id}:{ctx.service_status}"
            )
            if text:
                return text
        return brigade_reply(data, question)

    async def service(self, ctx: DdsCallContext, target: str, history: list[CallMessage], question: str) -> str:
        short, status = ctx.services.get(target, (target, "added"))
        data = {"service_short": short, "card_number": ctx.card_number, "service_status_title": status}
        if self._online(AITask.SERVICE_ACTOR):
            system = load_prompt(AITask.SERVICE_ACTOR).format(
                service=short, context=json.dumps(data, ensure_ascii=False)
            )
            text = await self._ask(AITask.SERVICE_ACTOR, system, history, question, f"{ctx.card_id}:{target}:{status}")
            if text:
                return text
        return service_reply(data, question)
