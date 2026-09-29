"""Голосовой полигон (п. 3.6): страница из прототипа ходит в тренажёр, а не во внешний сервис."""

from fastapi.testclient import TestClient

from aiskra.modules.training.application.voice_lab import split_directive
from tests.integration.conftest import login

API = "/api/v1/training/voice-lab"


def test_requires_sign_in(client: TestClient) -> None:
    assert client.post(f"{API}/chat", json={"messages": [{"role": "user", "content": "Алло"}]}).status_code == 401


def test_chat_streams_reply_in_openai_format(client: TestClient) -> None:
    login(client, "student")
    r = client.post(
        f"{API}/chat",
        json={
            "messages": [
                {"role": "system", "content": "Ты звонящий."},
                {"role": "user", "content": "Служба 112, что случилось?"},
            ]
        },
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert '"delta"' in r.text and r.text.rstrip().endswith("data: [DONE]")


def test_speech_without_providers_is_a_clear_error(client: TestClient) -> None:
    login(client, "student")
    assert client.post(f"{API}/tts", json={"input": "(speak with fear) Помогите!"}).status_code == 422
    assert client.post(f"{API}/stt", json={"audio": "AAAA", "format": "webm"}).status_code == 422


def test_directive_goes_to_style_not_text() -> None:
    assert split_directive("(speak in Russian with fear; fast pace) Помогите, пожар!") == (
        "speak in Russian with fear; fast pace",
        "Помогите, пожар!",
    )
    assert split_directive("Просто текст") == (None, "Просто текст")
