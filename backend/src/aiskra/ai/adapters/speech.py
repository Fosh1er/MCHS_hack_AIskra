"""Речь (п. 3.1, 1.4): заглушки офлайн-режима и распознавание через OpenAI-совместимый `/audio/transcriptions` —
локальный Whisper (Speaches, faster-whisper на GPU/CPU) или внешний API (OpenRouter) на демо."""

from __future__ import annotations

import io
import os
import wave

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


class FakeTTS:
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
