"""F1: ответ модели по мере генерации — адаптер, кеш, маршрутизатор, агенты, движок профиля, ремарки."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from aiskra.ai.adapters import caching
from aiskra.ai.adapters.caching import CachingLLM
from aiskra.ai.adapters.fake import FakeLLM
from aiskra.ai.adapters.openai_compatible import DONE, OpenAICompatibleLLM, parse_sse_delta
from aiskra.ai.ports import CacheDirective, ChatMessage, LLMParams, LLMResult
from aiskra.ai.router import ModelRouter, TaskProfile
from aiskra.ai.tasks import AITask
from aiskra.modules.training.application.actors import Actors
from aiskra.modules.training.application.psy import PsyDirector, TurnSignals, start_psy
from aiskra.modules.training.domain.stream_text import RemarkFilter
from aiskra.shared.cache import InMemoryTTLCache
from aiskra.shared.errors import ExternalServiceError
from tests.unit.test_psy import CATALOG, LEGEND

MSGS = [ChatMessage(role="user", content="Служба 112, что случилось?")]


def collect(gen: AsyncIterator[str]) -> list[str]:
    async def run() -> list[str]:
        return [p async for p in gen]

    return asyncio.run(run())


def sse(*events: str) -> bytes:
    return "".join(f"{e}\n\n" for e in events).encode()


def test_sse_lines_parsed_like_openai() -> None:
    assert parse_sse_delta('data: {"choices":[{"delta":{"content":"Пожар"}}]}') == "Пожар"
    assert parse_sse_delta('data: {"choices":[{"delta":{"role":"assistant"}}]}') is None
    assert parse_sse_delta(": OPENROUTER PROCESSING") is None  # комментарий шлюза
    assert parse_sse_delta("data: [DONE]") is DONE
    with pytest.raises(ExternalServiceError):
        parse_sse_delta('data: {"error": {"message": "provider overloaded"}}')


def _llm(handler: httpx.MockTransport) -> OpenAICompatibleLLM:
    return OpenAICompatibleLLM(name="demo", base_url="http://llm.test/v1", model="m", transport=handler)


def test_adapter_streams_pieces_until_done() -> None:
    seen: dict[str, Any] = {}

    def reply(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read()
        body = sse(
            'data: {"choices":[{"delta":{"role":"assistant"}}]}',
            'data: {"choices":[{"delta":{"content":"Горит "}}]}',
            'data: {"choices":[{"delta":{"content":"кухня!"}}]}',
            "data: [DONE]",
            'data: {"choices":[{"delta":{"content":"лишнее"}}]}',
        )
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    pieces = collect(_llm(httpx.MockTransport(reply)).stream(MSGS, params=LLMParams(task="t")))
    assert pieces == ["Горит ", "кухня!"]
    assert b'"stream":true' in seen["body"].replace(b" ", b"")


def test_adapter_stream_errors_are_external_service_errors() -> None:
    down = httpx.MockTransport(lambda r: httpx.Response(503, text="busy"))
    with pytest.raises(ExternalServiceError):
        collect(_llm(down).stream(MSGS, params=LLMParams(task="t")))
    broken = httpx.MockTransport(
        lambda r: httpx.Response(
            200, content=sse('data: {"choices":[{"delta":{"content":"Го"}}]}', 'data: {"error":{"message":"x"}}')
        )
    )
    with pytest.raises(ExternalServiceError):
        collect(_llm(broken).stream(MSGS, params=LLMParams(task="t")))


def test_cache_replays_stream_and_stores_only_complete_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(caching, "REPLAY_DELAY_S", 0)
    inner = FakeLLM(name="demo", fixtures={"t": "Горит кухня, третий этаж"})
    llm = CachingLLM(inner, InMemoryTTLCache())
    params = LLMParams(task="t", cache=CacheDirective(mode="task", scope="s"))
    first = collect(llm.stream(MSGS, params=params))
    second = collect(llm.stream(MSGS, params=params))
    assert "".join(first) == "".join(second) == "Горит кухня, третий этаж"
    assert len(inner.calls) == 1 and len(second) > 1  # из кеша — тоже по кускам


def test_cache_stream_falls_back_to_complete_for_non_streaming_models() -> None:
    class Whole:
        provider_name, model_id = "demo", "whole"

        async def complete(self, messages: Any, *, params: Any, schema: Any = None) -> LLMResult:
            return LLMResult(text="Целиком", provider="demo", model="whole", latency_ms=1)

        async def aclose(self) -> None: ...

    llm = CachingLLM(Whole(), InMemoryTTLCache())  # type: ignore[arg-type]
    assert collect(llm.stream(MSGS, params=LLMParams(task="t"))) == ["Целиком"]


def test_remark_filter_keeps_remarks_out_of_the_text() -> None:
    f = RemarkFilter()
    out = "".join(f.feed(ch) for ch in "[плачет] Помогите, [кашляет]горит!")
    assert out == " Помогите, горит!" and f.take_remarks() == ["плачет", "кашляет"]
    g = RemarkFilter()
    assert g.feed("[" + "а" * 100) == "[" + "а" * 100  # не ремарка — длинный текст после скобки
    h = RemarkFilter()
    assert h.feed("Адрес [Тверская") == "Адрес " and h.flush() == "[Тверская"


def _router(llm: Any) -> ModelRouter:
    tasks = [AITask.APPLICANT_ACTOR, AITask.PSY_ACTS]
    return ModelRouter(
        profiles={t: TaskProfile(task=t, provider="demo") for t in tasks},
        clients={"demo": llm, "fake": FakeLLM()},
        default_provider="fake",
    )


class Sink:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, kind: str, data: dict[str, Any]) -> None:
        self.events.append((kind, data))

    def kinds(self) -> list[str]:
        return [k for k, _ in self.events]


def test_actor_streams_tokens_and_reports_the_model() -> None:
    actors = Actors(_router(FakeLLM(name="demo", model="demo-m", fixtures={AITask.APPLICANT_ACTOR: "Горит кухня!"})))
    sink = Sink()
    text, _ = asyncio.run(actors.applicant(LEGEND, [], "Что случилось?", ["opening"], "s", sink=sink))
    assert text == "Горит кухня!"
    assert sink.kinds()[0] == "model" and sink.events[0][1]["model"] == "demo-m"
    assert "".join(d["text"] for k, d in sink.events if k == "token") == "Горит кухня!"


def test_model_failure_mid_stream_is_replaced_by_offline_reply() -> None:
    class Breaking:
        provider_name, model_id = "demo", "breaking"

        async def complete(self, messages: Any, *, params: Any, schema: Any = None) -> LLMResult:
            raise ExternalServiceError("нет")

        async def stream(self, messages: Any, *, params: Any) -> AsyncIterator[str]:
            yield "Горит "
            raise ExternalServiceError("обрыв")

        async def aclose(self) -> None: ...

    actors = Actors(_router(Breaking()))
    sink = Sink()
    text, _ = asyncio.run(actors.applicant(LEGEND, [], "Что случилось?", ["opening"], "s", sink=sink))
    assert text and text != "Горит"  # офлайн-ответ по легенде
    assert sink.kinds()[-1] == "replace"


def test_psy_turn_reports_state_before_the_answer_and_replace_on_rejection() -> None:
    llm = FakeLLM(name="demo", fixtures={AITask.APPLICANT_ACTOR: "[плачет] Тверская, дом семь, быстрее!"})
    director = PsyDirector(CATALOG, Actors(_router(llm)))
    p = CATALOG.get("panic")
    assert p is not None
    psy = start_psy(p, seed=3, catalog_version=1, settings={}, session_id=None)
    sink = Sink()
    turn = asyncio.run(director.turn(psy, LEGEND, [], "Успокойтесь!", ["opening"], 5, TurnSignals(), "s", sink=sink))
    assert turn is not None and turn.party_meta["source"] == "offline"
    kinds = sink.kinds()
    assert kinds.index("state") < kinds.index("token")  # состояние — до ответа
    state = sink.events[kinds.index("state")][1]
    assert state["level_after"] == 5 and state["acts"] and state["tone"]["emotion"]
    assert kinds[-1] == "replace"  # адрес закрыт на уровне 5 — ответ модели отклонён


def test_task_model_without_stream_yields_whole_answer() -> None:
    class Whole:
        provider_name, model_id = "demo", "whole"

        async def complete(self, messages: Any, *, params: Any, schema: Any = None) -> LLMResult:
            return LLMResult(text="Целиком", provider="demo", model="whole", latency_ms=1)

        async def aclose(self) -> None: ...

    router = ModelRouter(profiles={}, clients={"fake": Whole()}, default_provider="fake")  # type: ignore[dict-item]
    assert collect(router.for_task("x").stream(MSGS)) == ["Целиком"]
