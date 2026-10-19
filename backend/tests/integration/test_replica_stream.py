"""F1 через HTTP: ответ собеседника потоком SSE, сохранение реплики целиком, озвучка фразы до конца ответа."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any, NoReturn

import pytest
from fastapi.testclient import TestClient

from aiskra.ai.adapters import caching
from aiskra.ai.adapters.caching import CachingLLM
from aiskra.ai.adapters.fake import FakeLLM
from aiskra.ai.tasks import AITask
from aiskra.shared.cache import InMemoryTTLCache
from aiskra.shared.errors import ExternalServiceError
from tests.integration.test_journal import app_client as journal_app_client  # noqa: F401
from tests.integration.test_journal import as_user
from tests.integration.test_speech_audio import RecordingTTS


@pytest.fixture(scope="module")
def app_client(journal_app_client: Callable[[], TestClient]) -> Iterator[Callable[[], TestClient]]:  # noqa: F811
    yield journal_app_client


def events(body: str) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def _call(student: TestClient) -> str:
    call = student.post("/api/v1/training/calls/incoming", json={}).json()
    student.post(f"/api/v1/training/calls/{call['call_id']}/answer", json={})
    return str(call["call_id"])


def test_offline_stream_reports_state_and_rules_answer(app_client: Callable[[], TestClient]) -> None:
    student = as_user(app_client, "student")
    cid = _call(student)
    r = student.post(f"/api/v1/training/calls/{cid}/replicas/stream", json={"text": "Служба 112, что случилось?"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    ev = events(r.text)
    kinds = [k for k, _ in ev]
    assert kinds[0] == "accepted" and kinds[-1] == "final" and "state" in kinds and "token" not in kinds
    final = ev[-1][1]
    assert final["text"] and final["message_id"] and final["metrics"]["source"] == "rules"
    saved = student.get(f"/api/v1/training/calls/{cid}").json()["messages"]
    assert saved[-1]["text"] == final["text"] and saved[-2]["text"] == "Служба 112, что случилось?"


def test_model_answer_streams_tokens_and_is_saved_whole(
    app_client: Callable[[], TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    student = as_user(app_client, "student")
    cid = _call(student)
    router = student.app.state.services.model_router  # type: ignore[attr-defined]
    online = FakeLLM(name="demo", model="demo-m", fixtures={AITask.APPLICANT_ACTOR: "Горит кухня, третий этаж!"})
    monkeypatch.setitem(router._clients, "fake", CachingLLM(online, InMemoryTTLCache()))
    monkeypatch.setattr(caching, "REPLAY_DELAY_S", 0)

    r = student.post(f"/api/v1/training/calls/{cid}/replicas/stream", json={"text": "Что горит?"})
    ev = events(r.text)
    kinds = [k for k, _ in ev]
    assert kinds.index("state") < kinds.index("model") < kinds.index("token")
    streamed = "".join(d["text"] for k, d in ev if k == "token")
    final = ev[-1][1]
    assert streamed.strip() == final["text"] == "Горит кухня, третий этаж!"
    m = final["metrics"]
    assert m["source"] == "llm" and m["model"] == "demo-m" and m["ttft_ms"] is not None and m["pieces"] >= 3
    assert student.get(f"/api/v1/training/calls/{cid}").json()["messages"][-1]["text"] == final["text"]


class DownLLM:
    """Модель недоступна (порт закрыт): отказ до первого куска ответа."""

    provider_name = "demo"
    model_id = "demo-m"

    async def complete(self, *args: object, **kwargs: object) -> NoReturn:
        raise ExternalServiceError("demo: модель недоступна (ConnectError)")

    async def stream(self, *args: object, **kwargs: object) -> AsyncIterator[str]:
        raise ExternalServiceError("demo: модель недоступна (ConnectError)")
        yield ""  # pragma: no cover — делает метод асинхронным генератором

    async def aclose(self) -> None:
        return None


def test_model_down_answer_is_marked_rules_not_llm(
    app_client: Callable[[], TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    """F6.5 (e2e «модель остановлена»): ответ по правилам не подписывается «ИИ · модель» — событие `offline`."""
    student = as_user(app_client, "student")
    cid = _call(student)
    router = student.app.state.services.model_router  # type: ignore[attr-defined]
    monkeypatch.setitem(router._clients, "fake", DownLLM())

    r = student.post(f"/api/v1/training/calls/{cid}/replicas/stream", json={"text": "Сколько людей в квартире?"})
    ev = events(r.text)
    kinds = [k for k, _ in ev]
    assert kinds.index("model") < kinds.index("offline") < kinds.index("final") and "token" not in kinds
    final = ev[-1][1]
    assert final["text"] and final["metrics"]["source"] == "rules" and final["metrics"]["model"] is None
    assert student.get(f"/api/v1/training/calls/{cid}").json()["messages"][-1]["text"] == final["text"]


def test_stream_errors_come_as_events(app_client: Callable[[], TestClient]) -> None:
    student = as_user(app_client, "student")
    r = student.post(
        "/api/v1/training/calls/00000000-0000-0000-0000-000000000000/replicas/stream", json={"text": "Алло"}
    )
    ev = events(r.text)
    assert ev[-1][0] == "error" and ev[-1][1]["code"] == "call_not_found"
    anon = app_client()
    assert anon.post(f"/api/v1/training/calls/{_call(student)}/replicas/stream", json={"text": "x"}).status_code == 401


def test_fragment_is_spoken_in_the_callers_state(app_client: Callable[[], TestClient]) -> None:
    student = as_user(app_client, "student")
    cid = _call(student)
    url = f"/api/v1/training/calls/{cid}/speak"
    params = {"text": "Горит кухня!", "emotion": "panic", "pace": "very_fast", "volume": "loud", "breathing": "rapid"}
    off = student.get(url, params=params)
    assert off.status_code == 422 and off.json()["error"] == "tts_disabled"
    services = student.app.state.services  # type: ignore[attr-defined]
    real, stub = services.tts, RecordingTTS()
    services.tts = stub
    try:
        r = student.get(url, params=params)
        assert r.status_code == 200 and r.content == b"RIFF-stub-audio"
        text, profile = stub.calls[-1]
        assert text == "Горит кухня!" and profile.emotion == "panic" and profile.speed == 1.3
        assert profile.style and "panicking" in profile.style
    finally:
        services.tts = real
