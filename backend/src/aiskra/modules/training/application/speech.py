"""Голосовой ввод оператора и диспетчера (п. 1.4, 2.3): реплика в трубку записывается в браузере, распознаётся
моделью речи (Whisper за `STTPort`) и уходит собеседнику как обычная текстовая реплика."""

from __future__ import annotations

from dataclasses import dataclass

from aiskra.ai.ports import STTPort
from aiskra.shared.application import Command
from aiskra.shared.errors import DomainError
from aiskra.shared.security import Principal

MAX_AUDIO_BYTES = 3 * 1024 * 1024  # ≈ 1,5–3 мин речи в webm/opus — реплика в трубку заметно короче


@dataclass(frozen=True, kw_only=True)
class Transcribe(Command):
    actor: Principal
    audio: bytes
    mime: str = "audio/webm"


@dataclass(frozen=True)
class Transcribed:
    text: str


class TranscribeHandler:
    def __init__(self, stt: STTPort) -> None:
        self._stt = stt

    @property
    def enabled(self) -> bool:
        return self._stt.enabled

    async def __call__(self, cmd: Transcribe) -> Transcribed:
        if not self._stt.enabled:
            raise DomainError("Голосовой ввод не настроен — вводите реплику текстом", code="stt_disabled")
        if not cmd.audio:
            raise DomainError("Пустая запись", code="empty_audio")
        if len(cmd.audio) > MAX_AUDIO_BYTES:
            raise DomainError("Запись слишком длинная — реплика в трубку до минуты", code="audio_too_long")
        t = await self._stt.transcribe(cmd.audio, mime=cmd.mime)
        return Transcribed(text=t.text)
