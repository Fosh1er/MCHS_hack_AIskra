"""ИИ-путь сценариев и агентов (п. 3.2, 3.3): с «настоящей» моделью (FakeLLM под другим именем) ответы берутся
у модели, промпт содержит легенду без эталона; ошибка модели → офлайн-ответ."""

import asyncio
import random

from aiskra.ai.adapters.fake import FakeLLM
from aiskra.ai.ports import ChatMessage
from aiskra.ai.router import ModelRouter, TaskProfile
from aiskra.ai.tasks import AITask
from aiskra.modules.training.application.actors import Actors
from aiskra.modules.training.application.commands.scenarios import ScenarioGenerator
from aiskra.modules.training.domain.scenario import AddressFacts, IncidentFacts, ServiceFacts
from aiskra.shared.errors import ExternalServiceError

FIRE = IncidentFacts(
    code="1010101",
    group_id=1,
    group_title="Пожары",
    card_type="101",
    card_type_title="101",
    sign1="на улице",
    sign2="мусор",
    sign3="открытое пламя",
    final_type="пожар: мусор",
    flags=[],
)
ADDR = AddressFacts("Тверская улица", "7", "", "", "tverskoy", "Тверской", "CAO", 55.76, 37.61)


class Facts:
    async def pick_incident(self, rng: random.Random, groups: list[int] | None) -> IncidentFacts:
        return FIRE

    async def pick_address(self, rng: random.Random) -> AddressFacts:
        return ADDR

    async def resolve_services(self, *_: object) -> list[ServiceFacts]:
        return [ServiceFacts("S101", "Служба 101", True, "")]


def router(llm: FakeLLM) -> ModelRouter:
    tasks = [AITask.SCENARIO_GENERATION, AITask.APPLICANT_ACTOR, AITask.BRIGADE_ACTOR, AITask.SERVICE_ACTOR]
    return ModelRouter(
        profiles={t: TaskProfile(task=t, provider="demo") for t in tasks},
        clients={"demo": llm},
        default_provider="demo",
    )


def test_generator_uses_model_story() -> None:
    story = {
        "description": "Во дворе горит мусорный бак, дым идёт в окна",
        "opening": "Алло! У нас во дворе пожар!",
        "details": "бак у третьего подъезда",
    }
    llm = FakeLLM(name="demo", fixtures={AITask.SCENARIO_GENERATION: story})
    s = asyncio.run(ScenarioGenerator(Facts(), router(llm)).generate(random.Random(1), [], 2, None))
    assert s.source == "ai" and s.legend["opening"] == story["opening"] and s.legend["details"] == story["details"]
    assert s.reference_card["incident_types"] == ["1010101"]  # эталон — правилами, не моделью


def test_applicant_prompt_hides_reference() -> None:
    seen: list[list[ChatMessage]] = []

    def answer(messages: list[ChatMessage]) -> str:
        seen.append(messages)
        return "Тверская, семь!"

    llm = FakeLLM(name="demo", fixtures={AITask.APPLICANT_ACTOR: answer})
    legend = {
        "applicant": {"name": "Иванов"},
        "address": {"label": "Тверская улица, 7"},
        "what": "горит мусор",
        "emotion": "в панике",
    }
    text, revealed = asyncio.run(Actors(router(llm)).applicant(legend, [], "Какой адрес?", [], "s1"))
    assert text == "Тверская, семь!" and revealed == ["address"]
    system = seen[0][0].content
    assert "Тверская улица, 7" in system and "в панике" in system and "1010101" not in system


def test_model_error_falls_back_to_offline() -> None:
    class Broken(FakeLLM):
        async def complete(self, *a: object, **k: object):  # type: ignore[no-untyped-def,override]
            raise ExternalServiceError("нет сети")

    legend = {"address": {"label": "Тверская улица, 7"}, "what": "горит мусор"}
    text, _ = asyncio.run(Actors(router(Broken(name="demo"))).applicant(legend, [], "Адрес?", [], "s1"))
    assert text.startswith("Тверская улица, 7")
