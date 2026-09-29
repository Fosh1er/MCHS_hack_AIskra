"""ИИ-судья блока «Работа с заявителем» (п. 3.6, задача `psy_judge`): аудиоконтроль по профстандарту 12.002,
ТФ C/04.6. Судья отвечает на бинарные вопросы с цитатой: на фактических пунктах LLM совпадает с экспертами
на уровне κ ≈ 0,88, на шкалах 1–5 — плохо (docs/research/psychology/03, раздел F4). Без модели — «не проверено»."""

from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel, Field

from aiskra.ai.ports import ChatMessage
from aiskra.ai.prompts import load_prompt
from aiskra.ai.router import ModelRouter
from aiskra.ai.tasks import AITask
from aiskra.modules.assessment.domain.psy_scoring import PsyAttempt
from aiskra.modules.assessment.domain.scoring import Criterion
from aiskra.shared.errors import ExternalServiceError

log = logging.getLogger(__name__)
QUESTIONS = {
    "polite": "вежлив, без сарказма и раздражения",
    "emotion": "на эмоции отвечает кратко и переводит в действие",
    "strategy": "стратегия соответствует уровню заявителя",
    "explains": "объясняет, зачем вопросы, и что помощь направлена",
    "honest": "не обещает того, что от него не зависит",
    "concise": "реплики короткие и понятные",
    "respect": "не осуждает, не спорит, не обесценивает",
}


class JudgeAnswer(BaseModel):
    key: str = Field(max_length=16)
    answer: Literal["да", "нет", "неприменимо"]
    quote: str = Field(default="", max_length=200)


class PsyJudgeOut(BaseModel):
    answers: list[JudgeAnswer] = Field(default_factory=list, max_length=10)


class PsyJudge:
    def __init__(self, router: ModelRouter) -> None:
        self._router = router

    async def check(self, a: PsyAttempt) -> Criterion | None:
        model = self._router.for_task(AITask.PSY_JUDGE)
        if model.provider_name == "fake":
            return None
        state = a.profile.get("state") or {}
        profile = json.dumps(
            {
                "профиль": a.profile.get("title"),
                "уровень_в_начале": a.profile.get("start"),
                "пик": state.get("peak"),
                "в_конце": state.get("level"),
            },
            ensure_ascii=False,
        )
        lines = []
        for t in a.turns:
            who = {"operator": "Оператор", "party": "Заявитель"}.get(t.speaker, "Система")
            level = f" [уровень {t.level}]" if t.speaker == "party" and t.level else ""
            remarks = f" ({', '.join(t.remarks)})" if t.remarks else ""
            lines.append(f"{t.at_s:>5.0f} с · {who}{level}{remarks}: {t.text}")
        system = load_prompt(AITask.PSY_JUDGE).replace("{profile}", profile).replace("{transcript}", "\n".join(lines))
        try:
            result = await model.complete(
                [ChatMessage(role="system", content=system), ChatMessage(role="user", content="Оцени звонок.")],
                schema=PsyJudgeOut,
            )
            out = (
                result.parsed
                if isinstance(result.parsed, PsyJudgeOut)
                else PsyJudgeOut.model_validate_json(result.text)
            )
        except (ExternalServiceError, ValueError) as e:
            log.warning("ИИ-судья блока «Работа с заявителем» недоступен: %s", e)
            return None
        rated = [x for x in out.answers if x.key in QUESTIONS and x.answer != "неприменимо"]
        if not rated:
            return None
        c = Criterion("psy_judge", round(sum(x.answer == "да" for x in rated) / len(rated), 3))
        c.errors = [f"{QUESTIONS[x.key]} — нет: «{x.quote}»" for x in rated if x.answer == "нет"]
        c.note = f"ИИ-судья: {len(rated)} вопросов аудиоконтроля"
        return c
