"""Голосовой ввод (п. 1.4): адаптер Whisper за OpenAI-совместимым API, конфиг речи, обработчик распознавания."""

from uuid import uuid4

import httpx
import pytest

from aiskra.ai.adapters.speech import FakeSTT, OpenAICompatibleSTT
from aiskra.ai.config import AIConfig
from aiskra.ai.ports import Transcript
from aiskra.modules.training.application.speech import MAX_AUDIO_BYTES, Transcribe, TranscribeHandler
from aiskra.shared.errors import DomainError, ExternalServiceError
from aiskra.shared.security import Principal, Role


async def test_whisper_adapter_sends_multipart_and_reads_text() -> None:
    seen: dict[str, object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"], seen["body"] = req.url.path, req.content
        return httpx.Response(200, json={"text": " Что у вас случилось? "})

    stt = OpenAICompatibleSTT(
        base_url="http://whisper:8000/v1", model="large-v3-turbo", transport=httpx.MockTransport(handler)
    )
    t = await stt.transcribe(b"\x1aE\xdf\xa3webm", mime="audio/webm;codecs=opus")
    assert t.text == "Что у вас случилось?" and seen["path"] == "/v1/audio/transcriptions"
    body = bytes(seen["body"])  # type: ignore[arg-type]
    assert b'filename="speech.webm"' in body and b"large-v3-turbo" in body and b'name="language"' in body


async def test_whisper_unavailable_is_service_error() -> None:
    stt = OpenAICompatibleSTT(
        base_url="http://whisper:8000/v1", model="m", transport=httpx.MockTransport(lambda r: httpx.Response(503))
    )
    with pytest.raises(ExternalServiceError):
        await stt.transcribe(b"x")


def test_external_stt_needs_allow_external_and_lan_is_internal() -> None:
    with pytest.raises(ValueError, match="stt"):
        AIConfig.model_validate({"stt": {"kind": "openai_compatible", "base_url": "https://openrouter.ai/api/v1"}})
    lan = AIConfig.model_validate({"stt": {"kind": "openai_compatible", "base_url": "http://192.168.31.20:8000/v1"}})
    assert lan.stt.model == "whisper-1"
    with pytest.raises(ValueError, match="base_url"):
        AIConfig.model_validate({"stt": {"kind": "openai_compatible"}})


async def test_handler_refuses_when_disabled_or_too_long() -> None:
    who = Principal(user_id=uuid4(), session_id=uuid4(), login="op1", full_name="Оператор", role=Role.STUDENT)
    off = TranscribeHandler(FakeSTT())
    assert not off.enabled
    with pytest.raises(DomainError, match="не настроен"):
        await off(Transcribe(actor=who, audio=b"x"))

    class Stub:
        enabled = True

        async def transcribe(self, audio: bytes, *, lang: str = "ru", mime: str = "audio/webm") -> Transcript:
            return Transcript(text="Назовите адрес")

    on = TranscribeHandler(Stub())  # type: ignore[arg-type]
    assert (await on(Transcribe(actor=who, audio=b"x"))).text == "Назовите адрес"
    with pytest.raises(DomainError, match="длинная"):
        await on(Transcribe(actor=who, audio=b"x" * (MAX_AUDIO_BYTES + 1)))
