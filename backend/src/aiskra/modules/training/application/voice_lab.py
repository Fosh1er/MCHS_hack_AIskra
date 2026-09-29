"""Голосовой полигон (п. 3.6, прототип zhamilka1/emotional-stt-tts): свободный голосовой разговор с эмоциональным
заявителем по сценариям страницы `frontend/public/voice-lab/`. Страница ведёт тональность сама, а сервер отвечает
на три её запроса через порты ИИ тренажёра: распознавание (STTPort), реплика (ModelRouter, задача applicant_actor)
и синтез (TTSPort). Внешние адреса и ключи — только в конфиге, как у остального тренажёра."""

from __future__ import annotations

import re
from dataclasses import dataclass

from aiskra.ai.ports import AudioBlob, ChatMessage, STTPort, TTSPort, VoiceProfile
from aiskra.ai.router import ModelRouter
from aiskra.ai.tasks import AITask
from aiskra.shared.errors import DomainError

MAX_TURNS = 10
MAX_CHARS = 4000
_DIRECTIVE = re.compile(r"^\s*\(([^)]{0,600})\)\s*")  # «(speak in Russian with fear…)» — подача, а не текст реплики


@dataclass(frozen=True, kw_only=True)
class LabMessage:
    role: str
    content: str


def split_directive(text: str) -> tuple[str | None, str]:
    """Подачу из скобок в начале — в стиль синтеза (ADR-0011: эмоция параметром провайдера), остальное — текст."""
    m = _DIRECTIVE.match(text)
    return (m.group(1).strip(), text[m.end() :].strip()) if m else (None, text.strip())


class VoiceLab:
    def __init__(self, stt: STTPort, tts: TTSPort, router: ModelRouter) -> None:
        self._stt, self._tts, self._router = stt, tts, router

    async def transcribe(self, audio: bytes, *, mime: str) -> str:
        if not self._stt.enabled:
            raise DomainError("Распознавание речи не настроено", code="stt_disabled")
        return (await self._stt.transcribe(audio, mime=mime)).text.strip()

    async def reply(self, messages: list[LabMessage]) -> str:
        chat = [
            ChatMessage(role=m.role, content=m.content[:12000])  # type: ignore[arg-type]
            for m in messages
            if m.role in ("system", "user", "assistant")
        ]
        system = [m for m in chat if m.role == "system"][:1]
        dialog = [m for m in chat if m.role != "system"][-MAX_TURNS:]
        if not dialog:
            raise DomainError("Нужна хотя бы одна реплика", code="empty_dialog")
        result = await self._router.for_task(AITask.APPLICANT_ACTOR).complete(system + dialog)
        return result.text.strip()

    async def speak(self, text: str, *, voice: str = "applicant_female") -> AudioBlob:
        if not self._tts.enabled:
            raise DomainError("Серверный синтез речи не настроен", code="tts_disabled")
        style, body = split_directive(text[:MAX_CHARS])
        if not body:
            raise DomainError("Пустой текст для синтеза", code="empty_text")
        return await self._tts.synthesize(body, voice=VoiceProfile(voice=voice, style=style))
