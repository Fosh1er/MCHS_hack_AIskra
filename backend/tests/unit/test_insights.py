"""ТЗ 3.13, 7.3: выводы по типичным ошибкам группы — моделью (задача insights) или правилами без неё."""

import asyncio
import json
from uuid import uuid4

from pydantic import BaseModel

from aiskra.ai.adapters.fake import FakeLLM
from aiskra.ai.ports import ChatMessage, LLMParams, LLMResult
from aiskra.ai.router import ModelRouter, TaskProfile
from aiskra.ai.tasks import AITask
from aiskra.modules.assessment.application.ports.attempts import AssessmentRecord
from aiskra.modules.assessment.application.queries.assessments import GroupInsights, GroupInsightsHandler
from aiskra.modules.assessment.domain.insights import rules_insights
from aiskra.shared.errors import ExternalServiceError


def test_weakest_criteria_become_insights_and_actions() -> None:
    r = rules_insights(
        [("services", "Службы", 0.42), ("timing", "Время заполнения", 0.6), ("type", "Тип происшествия", 0.95)],
        [("Службы: не направлено в: Служба 103", 7)],
        61.5,
        0.4,
    )
    assert "«Службы» — 42 %" in r.summary and "не выезжает" in r.summary
    assert len(r.insights) == 3 and "7 раз" in r.insights[-1]  # тип (95 %) — не слабое место
    assert r.actions[0].startswith("Повторить правило подбора служб")


def test_no_weak_spots() -> None:
    r = rules_insights([("type", "Тип происшествия", 0.9)], [], 92, 1.0)
    assert "явных слабых мест нет" in r.summary and r.actions


class Repo:
    async def recent(self, limit: int) -> list[AssessmentRecord]:
        crit = [{"key": "services", "title": "Службы", "score": 0.4, "errors": ["не направлено в: Служба 103"]}]
        return [
            AssessmentRecord(uuid4(), uuid4(), uuid4(), "112", None, 55, False, "rules", {"criteria": crit})
            for _ in range(3)
        ]


class Broken(FakeLLM):
    async def complete(
        self, messages: list[ChatMessage], *, params: LLMParams, schema: type[BaseModel] | None = None
    ) -> LLMResult:
        raise ExternalServiceError("нет связи", code="llm_unavailable")


def handler(llm: FakeLLM) -> GroupInsightsHandler:
    router = ModelRouter(
        profiles={AITask.INSIGHTS: TaskProfile(task=AITask.INSIGHTS, provider=llm.provider_name)},
        clients={llm.provider_name: llm},
        default_provider=llm.provider_name,
    )
    return GroupInsightsHandler(Repo(), router)  # type: ignore[arg-type]


def test_model_writes_insights_from_numbers_only() -> None:
    answer = {"summary": "Группа теряет службу 103.", "insights": ["Службы — 40 %"], "actions": ["Разобрать службы"]}
    llm = FakeLLM(name="demo", model="demo-model", fixtures={AITask.INSIGHTS: answer})
    r = asyncio.run(handler(llm)(GroupInsights()))
    assert r.source == "ai" and r.model == "demo-model" and r.summary == "Группа теряет службу 103."
    sent = json.loads(llm.calls[0][0][1].content)
    assert sent["попыток"] == 3 and sent["частые_ошибки"][0]["раз"] == 3


def test_model_failure_falls_back_to_rules() -> None:
    r = asyncio.run(handler(Broken(name="demo"))(GroupInsights()))
    assert r.source == "rules" and "«Службы» — 40 %" in r.summary


def test_offline_rules_without_calling_model() -> None:
    llm = FakeLLM()
    r = asyncio.run(handler(llm)(GroupInsights()))
    assert r.source == "rules" and r.summary and not llm.calls
