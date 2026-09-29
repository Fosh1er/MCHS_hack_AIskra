"""Речь: голосовой ввод (п. 1.4) — адаптер Whisper, конфиг, обработчик; голос собеседника (п. 3.6) — адаптер синтеза."""

import io
import json
import wave
from uuid import uuid4

import httpx
import pytest

from aiskra.ai.adapters.speech import FakeSTT, FakeTTS, OpenAICompatibleSTT, OpenAICompatibleTTS
from aiskra.ai.config import AIConfig
from aiskra.ai.ports import Transcript, VoiceProfile
from aiskra.modules.training.application.speech import (
    MAX_AUDIO_BYTES,
    Transcribe,
    TranscribeHandler,
    clip_for_speech,
    drop_phantoms,
)
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


# --- Голос собеседника (п. 3.6, V2): адаптер синтеза и конфиг ---


def tts_capture(**kwargs: object) -> tuple[OpenAICompatibleTTS, dict[str, object]]:
    seen: dict[str, object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"], seen["json"] = req.url.path, json.loads(req.content)
        seen["auth"] = req.headers.get("authorization")
        return httpx.Response(200, content=b"ID3mp3", headers={"content-type": "audio/mpeg"})

    tts = OpenAICompatibleTTS(
        base_url="https://openrouter.ai/api/v1",
        model="google/gemini-3.8-flash-lite-tts",
        voice="Zephyr",
        voices={"applicant_female": "Kore", "brigade": ""},
        transport=httpx.MockTransport(handler),
        **kwargs,  # type: ignore[arg-type]
    )
    return tts, seen


PANIC = VoiceProfile(voice="applicant_female", speed=1.3, emotion="panic", style="a panicking caller: very fast")


async def test_tts_style_google_goes_to_provider_options() -> None:
    tts, seen = tts_capture(style="google")
    blob = await tts.synthesize("Алло, у нас пожар!", voice=PANIC)
    body = seen["json"]
    assert seen["path"] == "/api/v1/audio/speech" and blob.mime == "audio/mpeg" and blob.content == b"ID3mp3"
    assert body == {
        "model": "google/gemini-3.8-flash-lite-tts",
        "input": "Алло, у нас пожар!",  # текст реплики без инструкции — её не прочитают вслух
        "response_format": "mp3",
        "speed": 1.3,
        "voice": "Kore",
        "provider": {"options": {"google-ai-studio": {"speech_metadata": {"style": PANIC.style}}}},
    }


async def test_tts_style_openai_and_none() -> None:
    tts, seen = tts_capture(style="openai")
    await tts.synthesize("Слушаю", voice=PANIC)
    assert seen["json"]["provider"] == {"options": {"openai": {"instructions": PANIC.style}}}  # type: ignore[index]
    tts, seen = tts_capture(style="none")
    await tts.synthesize("Слушаю", voice=VoiceProfile(voice="brigade", style="calm officer"))
    body = seen["json"]
    assert "provider" not in body and body["voice"] == "Zephyr" and body["speed"] == 1.0  # type: ignore[operator,index]


async def test_tts_pcm_wrapped_to_wav() -> None:
    pcm = b"\x01\x00" * 2400

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=pcm, headers={"content-type": "audio/pcm"})

    tts = OpenAICompatibleTTS(
        base_url="http://tts/v1", model="m", response_format="pcm", transport=httpx.MockTransport(handler)
    )
    blob = await tts.synthesize("Алло", voice=VoiceProfile())
    assert blob.mime == "audio/wav" and blob.content[:4] == b"RIFF" and blob.content.endswith(pcm)
    with wave.open(io.BytesIO(blob.content)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (24_000, 1, 2)


async def test_tts_error_is_service_error() -> None:
    for resp in (httpx.Response(503), httpx.Response(200, content=b"")):
        transport = httpx.MockTransport(lambda _, resp=resp: resp)  # type: ignore[misc]
        tts = OpenAICompatibleTTS(base_url="http://tts/v1", model="m", transport=transport)
        with pytest.raises(ExternalServiceError):
            await tts.synthesize("Алло", voice=VoiceProfile())


def test_external_tts_needs_allow_external() -> None:
    external = {"tts": {"kind": "openai_compatible", "base_url": "https://openrouter.ai/api/v1"}}
    with pytest.raises(ValueError, match="tts"):
        AIConfig.model_validate(external)
    assert AIConfig.model_validate({**external, "allow_external": True}).tts.style == "none"
    local = AIConfig.model_validate({"tts": {"kind": "openai_compatible", "base_url": "http://speaches:8000/v1"}})
    assert local.tts.cache_mb == 64 and local.tts.response_format == "mp3"
    assert not FakeTTS().enabled


def test_long_reply_clipped_by_sentence() -> None:
    text = "Алло! " + "Горит квартира, дым идёт в подъезд. " * 30
    clipped = clip_for_speech(text, 100)
    assert len(clipped) <= 100 and clipped.endswith(".")
    assert clip_for_speech("Короткая реплика") == "Короткая реплика"


def test_whisper_phantoms_dropped() -> None:
    """П. 3.6, V3: на тишине Whisper сочиняет титры — такие предложения не должны уйти собеседнику."""
    assert drop_phantoms("Продолжение следует...") == ""
    assert drop_phantoms("Субтитры сделал DimaTorzok") == ""
    assert drop_phantoms("Где вы находитесь? Продолжение следует...") == "Где вы находитесь?"
    assert drop_phantoms("Назовите адрес, пожалуйста.") == "Назовите адрес, пожалуйста."
