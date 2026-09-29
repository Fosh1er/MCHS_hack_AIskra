"""Речь (п. 3.1, 1.4, 3.6): заглушки офлайн-режима, распознавание через OpenAI-совместимый `/audio/transcriptions`
(локальный Whisper — Speaches, faster-whisper на GPU/CPU — или внешний API на демо) и синтез через `/audio/speech`
(OpenRouter — Gemini, OpenAI TTS — на демо; Speaches с Piper в изолированном контуре)."""

from __future__ import annotations

import asyncio
import io
import os
import wave
from typing import Any, Literal

import httpx

from aiskra.ai.ports import AudioBlob, Transcript, VoiceProfile
from aiskra.shared.errors import ExternalServiceError

EXT = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/wav": "wav", "audio/x-wav": "wav", "audio/mpeg": "mp3",
       "audio/mp4": "m4a", "audio/aac": "aac", "audio/flac": "flac"}  # fmt: skip


def _silence_wav(duration_s: float = 0.2, rate: int = 16_000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * duration_s))
    return buf.getvalue()


def pcm_to_wav(pcm: bytes, rate: int = 24_000) -> bytes:
    """Сырой звук 16 бит моно (Gemini TTS на OpenRouter отдаёт `pcm`) → WAV, который играет любой браузер."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


class FakeTTS:
    """Серверный синтез выключен: реплики озвучивает браузер (`CallPanel`)."""

    enabled = False
    model_id = "browser"

    def __init__(self) -> None:
        self.calls = 0

    async def synthesize(self, text: str, *, voice: VoiceProfile) -> AudioBlob:
        self.calls += 1
        return AudioBlob(content=_silence_wav(), mime="audio/wav")


class FakeSTT:
    enabled = False

    async def transcribe(self, audio: bytes, *, lang: str = "ru", mime: str = "audio/webm") -> Transcript:
        return Transcript(text="", confidence=None)


class OpenAICompatibleSTT:
    """Whisper за OpenAI-совместимым API: multipart `file` + `model` + `language`, ответ `{"text": …}`."""

    enabled = True

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key_env: str | None = None,
        language: str = "ru",
        timeout_s: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        key = os.environ.get(api_key_env, "") if api_key_env else ""
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {key}"} if key else {},
            timeout=timeout_s,
            transport=transport,
        )
        self._model, self._lang = model, language

    async def transcribe(self, audio: bytes, *, lang: str = "", mime: str = "audio/webm") -> Transcript:
        base = mime.split(";")[0].strip().lower()
        files = {"file": (f"speech.{EXT.get(base, 'webm')}", audio, base or "application/octet-stream")}
        data = {"model": self._model, "language": lang or self._lang, "response_format": "json", "temperature": "0"}
        try:
            resp = await self._http.post("/audio/transcriptions", files=files, data=data)
            resp.raise_for_status()
            body = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ExternalServiceError(f"распознавание речи недоступно ({exc.__class__.__name__}: {exc})") from exc
        return Transcript(text=str(body.get("text") or "").strip(), confidence=None)


MIME = {"mp3": "audio/mpeg", "wav": "audio/wav"}
Style = Literal["google", "openai", "none"]


class OpenAICompatibleTTS:
    """Синтез за OpenAI-совместимым `/audio/speech`: `{model, input, voice, response_format, speed}`.

    Эмоция не приписывается к тексту — модель без поддержки инструкций прочитала бы её вслух. Она уходит
    параметром провайдера (OpenRouter, `provider.options`): `google` → `speech_metadata.style`, `openai` →
    `instructions`. При `style: none` (Piper в Speaches) подача передаётся только темпом."""

    enabled = True

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key_env: str | None = None,
        voice: str = "",
        voices: dict[str, str] | None = None,
        style: Style = "none",
        response_format: Literal["mp3", "wav", "pcm"] = "mp3",
        pcm_rate: int = 24_000,
        timeout_s: float = 20.0,
        max_concurrency: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        key = os.environ.get(api_key_env, "") if api_key_env else ""
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {key}"} if key else {},
            timeout=timeout_s,
            transport=transport,
        )
        self._model, self._voice, self._voices = model, voice, dict(voices or {})
        self._style, self._format, self._rate = style, response_format, pcm_rate
        self._slots = asyncio.Semaphore(max_concurrency)  # синтез на CPU тяжёлый, внешний API — с лимитами

    @property
    def model_id(self) -> str:
        return self._model

    def _style_options(self, profile: VoiceProfile) -> dict[str, Any]:
        if not profile.style or self._style == "none":
            return {}
        if self._style == "google":
            return {"google-ai-studio": {"speech_metadata": {"style": profile.style}}}
        return {"openai": {"instructions": profile.style}}

    async def synthesize(self, text: str, *, voice: VoiceProfile) -> AudioBlob:
        body: dict[str, Any] = {
            "model": self._model,
            "input": text,
            "response_format": self._format,
            "speed": round(voice.speed, 2),
        }
        name = self._voices.get(voice.voice) or self._voice
        if name:  # у части моделей (Fish Audio) голос не задаётся
            body["voice"] = name
        if options := self._style_options(voice):
            body["provider"] = {"options": options}
        try:
            async with self._slots:
                resp = await self._http.post("/audio/speech", json=body)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ExternalServiceError(f"синтез речи недоступен ({exc.__class__.__name__}: {exc})") from exc
        if not resp.content:
            raise ExternalServiceError("синтез речи вернул пустой звук")
        if self._format == "pcm":
            return AudioBlob(content=pcm_to_wav(resp.content, self._rate), mime="audio/wav")
        mime = resp.headers.get("content-type", "").split(";")[0].strip() or MIME[self._format]
        return AudioBlob(content=resp.content, mime=mime)
