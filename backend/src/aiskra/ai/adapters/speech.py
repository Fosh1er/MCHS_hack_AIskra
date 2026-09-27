"""Заглушки речи (п. 3.1): офлайн-режим и тесты. Реальные адаптеры (Silero/Piper, Whisper/Vosk) — позже."""

from __future__ import annotations

import io
import wave

from aiskra.ai.ports import AudioBlob, Transcript, VoiceProfile


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
    async def transcribe(self, audio: bytes, *, lang: str = "ru") -> Transcript:
        return Transcript(text="", confidence=None)
