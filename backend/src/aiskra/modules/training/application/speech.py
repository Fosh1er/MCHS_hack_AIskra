"""Речь в звонке.

- Голосовой ввод оператора и диспетчера (п. 1.4, 2.3): реплика в трубку записывается в браузере, распознаётся
  моделью речи (Whisper за `STTPort`) и уходит собеседнику как обычная текстовая реплика.
- Голос собеседника (п. 3.6, V2): реплика озвучивается на сервере (`TTSPort`) голосом его роли и с подачей по
  снимку состояния заявителя у этой реплики. Звук — отдельным запросом: текст, по которому оператор заполняет
  карточку, приходит без ожидания синтеза.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from uuid import UUID

from aiskra.ai.ports import STTPort, TTSPort, VoiceProfile
from aiskra.modules.training.application.ports.scenarios import CallRepository, ScenarioRepository
from aiskra.modules.training.application.queries.calls import call_visible
from aiskra.modules.training.domain.audio import join_call_audio
from aiskra.modules.training.domain.call import Call, CallMessage, CallParty, Speaker
from aiskra.modules.training.domain.scenario import legend_voice
from aiskra.modules.training.domain.tone import STAFF_STYLE, speech_speed, speech_style
from aiskra.shared.application import Command, Query
from aiskra.shared.errors import DomainError, ExternalServiceError, NotFoundError
from aiskra.shared.security import Principal

log = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 3 * 1024 * 1024  # ≈ 1,5–3 мин речи в webm/opus — реплика в трубку заметно короче

# Whisper на тишине и шуме «досочиняет» титры из видео, на которых учился: «Продолжение следует…», «Субтитры сделал
# DimaTorzok». В режиме без рук шум попадает в распознавание чаще — такие предложения выбрасываем: оператор 112 их
# не произносит, а собеседник получил бы бессмыслицу (п. 3.6, V3).
_PHANTOM = re.compile(
    r"субтитр|продолжение следует|спасибо за просмотр|подписывайтесь|ставьте лайк|dimatorzok", re.IGNORECASE
)
_SENTENCE = re.compile(r"(?<=[.!?…])\s+")


def drop_phantoms(text: str) -> str:
    """Убрать из распознанного текста предложения-галлюцинации Whisper, остальное оставить."""
    return " ".join(p for p in _SENTENCE.split(text.strip()) if p and not _PHANTOM.search(p)).strip()


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
        return Transcribed(text=drop_phantoms(t.text))


@dataclass(frozen=True)
class SpeechStatus:
    """Что из речи настроено: распознавание (кнопка «говорить») и серверный синтез (иначе — голос браузера)."""

    stt: bool
    tts: bool


MAX_TTS_CHARS = 600  # реплика собеседника — 1–2 фразы; длиннее — обрезаем по предложению, а не посреди слова


def clip_for_speech(text: str, limit: int = MAX_TTS_CHARS) -> str:
    if len(text) <= limit:
        return text
    head = text[:limit]
    cut = max((m.end() for m in re.finditer(r"[.!?…]\s", head)), default=0)
    return head[:cut].strip() if cut else head.rsplit(" ", 1)[0]


@dataclass(frozen=True, kw_only=True)
class GetReplicaAudio(Query):
    actor: Principal
    call_id: UUID
    message_id: UUID


@dataclass(frozen=True)
class ReplicaAudio:
    content: bytes
    mime: str


class _Voices:
    """Голос и подача реплик звонка — общие для звука реплики и записи звонка."""

    def __init__(self, tts: TTSPort, calls: CallRepository, scenarios: ScenarioRepository) -> None:
        self._tts = tts
        self._calls = calls
        self._scenarios = scenarios

    async def _voice(self, party: CallParty, scenario_id: UUID | None) -> str:
        """Роль голоса; имя голоса провайдера подставит адаптер по `tts.voices` конфига."""
        if party is not CallParty.APPLICANT:
            return party.value  # brigade | service
        scenario = await self._scenarios.get(scenario_id) if scenario_id else None
        applicant = scenario.legend.get("applicant", {}) if scenario else {}
        sex = legend_voice(applicant) if isinstance(applicant, dict) else None
        return f"applicant_{sex}" if sex else "applicant"

    async def _profile(self, call: Call, msg: CallMessage) -> VoiceProfile:
        if msg.speaker is Speaker.OPERATOR:  # запись звонка (п. 8.7): оператор — ровным голосом роли «operator»
            return VoiceProfile(voice="operator", style=STAFF_STYLE)
        if msg.tone is not None:
            return VoiceProfile(
                voice=await self._voice(call.party, call.scenario_id),
                speed=speech_speed(msg.tone),
                emotion=msg.tone.emotion,
                style=speech_style(msg.tone),
            )
        # старший группы и диспетчер службы — ровная деловая подача; реплика заявителя до п. 3.6 — без стиля
        staff = call.party is not CallParty.APPLICANT
        return VoiceProfile(voice=await self._voice(call.party, call.scenario_id), style=STAFF_STYLE if staff else None)


class ReplicaAudioHandler(_Voices):
    """Звук реплики собеседника. Видит тот же, кто видит звонок: свой — обучающийся, любой — преподаватель."""

    async def __call__(self, q: GetReplicaAudio) -> ReplicaAudio:
        call = await self._calls.get(q.call_id)
        if call is None or not call_visible(call, q.actor):
            raise NotFoundError("Звонок не найден", code="call_not_found")
        msg = next((m for m in await self._calls.messages(call.id) if m.id == q.message_id), None)
        if msg is None or msg.speaker is not Speaker.PARTY:
            raise NotFoundError("Реплики собеседника нет", code="replica_not_found")
        if not self._tts.enabled:
            raise DomainError("Серверный синтез речи не настроен — озвучивает браузер", code="tts_disabled")
        profile = await self._profile(call, msg)
        try:
            blob = await self._tts.synthesize(clip_for_speech(msg.text), voice=profile)
        except ExternalServiceError as e:  # интерфейс озвучит реплику браузером — здесь только запись в журнал
            log.warning("Синтез речи (%s) недоступен: %s", self._tts.model_id, e)
            raise
        return ReplicaAudio(content=blob.content, mime=blob.mime)


MAX_RECORDING_REPLICAS = 80  # учебный звонок — 10–30 реплик; предел защищает синтез от очень длинных разговоров


@dataclass(frozen=True, kw_only=True)
class GetCallRecording(Query):
    actor: Principal
    call_id: UUID


@dataclass(frozen=True)
class CallRecording:
    content: bytes
    mime: str
    file_name: str


class CallRecordingHandler(_Voices):
    """Запись звонка одним файлом (п. 8.7): реплики оператора и собеседника по порядку, озвученные серверным синтезом
    (голос и подача — как при разговоре), с паузами. WAV — если синтез отдаёт WAV/PCM, иначе MP3. Голос оператора
    в трубке не хранится (распознаётся в текст), поэтому его реплики тоже синтезируются."""

    async def __call__(self, q: GetCallRecording) -> CallRecording:
        call = await self._calls.get(q.call_id)
        if call is None or not call_visible(call, q.actor):
            raise NotFoundError("Звонок не найден", code="call_not_found")
        if not self._tts.enabled:
            raise DomainError("Запись звонка требует серверного синтеза речи (конфиг tts)", code="tts_disabled")
        spoken = [m for m in await self._calls.messages(call.id) if m.speaker is not Speaker.SYSTEM and m.text.strip()]
        if not spoken:
            raise DomainError("В звонке нет реплик", code="empty_call")
        segments = []
        try:
            for m in spoken[:MAX_RECORDING_REPLICAS]:
                blob = await self._tts.synthesize(clip_for_speech(m.text), voice=await self._profile(call, m))
                segments.append(blob.content)
        except ExternalServiceError as e:
            log.warning("Запись звонка: синтез речи (%s) недоступен: %s", self._tts.model_id, e)
            raise
        content, ext = join_call_audio(segments)
        stamp = call.started_at.strftime("%Y%m%d-%H%M")
        return CallRecording(
            content=content, mime="audio/wav" if ext == "wav" else "audio/mpeg", file_name=f"call-{stamp}.{ext}"
        )
