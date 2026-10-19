"""F3: основная модель речи не ответила — резервная; конфиг демо-стенда собирает обе."""

import asyncio
from pathlib import Path

import pytest

from aiskra.ai.adapters import factory
from aiskra.ai.adapters.caching import CachingTTS
from aiskra.ai.adapters.speech import FallbackSTT, FallbackTTS
from aiskra.ai.config import load_ai_config
from aiskra.ai.ports import AudioBlob, Transcript, VoiceProfile
from aiskra.shared.errors import ExternalServiceError

CONFIG = Path(__file__).resolve().parents[3] / "config" / "ai.openrouter.yaml"


class Speech:
    def __init__(self, name: str, *, fail: bool = False) -> None:
        self.model_id, self.enabled, self.fail, self.calls = name, True, fail, 0

    async def synthesize(self, text: str, *, voice: VoiceProfile) -> AudioBlob:
        self.calls += 1
        if self.fail:
            raise ExternalServiceError(f"{self.model_id}: 503")
        return AudioBlob(content=self.model_id.encode(), mime="audio/wav")

    async def transcribe(self, audio: bytes, *, lang: str = "", mime: str = "audio/webm") -> Transcript:
        self.calls += 1
        if self.fail:
            raise ExternalServiceError(f"{self.model_id}: 503")
        return Transcript(text=self.model_id)


def test_tts_uses_backup_only_when_primary_fails() -> None:
    ok, backup = Speech("gemini"), Speech("mai")
    assert asyncio.run(FallbackTTS(ok, backup).synthesize("Алло", voice=VoiceProfile())).content == b"gemini"
    assert backup.calls == 0
    broken = Speech("gemini", fail=True)
    assert asyncio.run(FallbackTTS(broken, backup).synthesize("Алло", voice=VoiceProfile())).content == b"mai"
    with pytest.raises(ExternalServiceError):  # обе не ответили — ошибка, интерфейс озвучит браузером
        asyncio.run(FallbackTTS(broken, Speech("mai", fail=True)).synthesize("Алло", voice=VoiceProfile()))


def test_stt_uses_backup_only_when_primary_fails() -> None:
    assert asyncio.run(FallbackSTT(Speech("qwen"), Speech("whisper")).transcribe(b"x")).text == "qwen"
    assert asyncio.run(FallbackSTT(Speech("qwen", fail=True), Speech("whisper")).transcribe(b"x")).text == "whisper"


def test_demo_config_builds_chosen_models_with_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("TTS_KIND", "STT_KIND"):
        monkeypatch.setenv(k, "openai_compatible")
    monkeypatch.setenv("AISKRA_AI_ALLOW_EXTERNAL", "true")
    cfg = load_ai_config(CONFIG)
    assert cfg.tts.model == "google/gemini-3.8-flash-tts" and cfg.tts.voice == "Zephyr"
    assert cfg.tts.fallback is not None and cfg.tts.fallback.model == "microsoft/mai-voice-2.1-flash"
    assert cfg.tts.fallback.voice == "ru-RU-Masha:MAI-Voice-2.1-Flash"
    assert cfg.stt.model == "qwen/qwen3-asr-0.6b" and cfg.stt.fallback_model == "openai/whisper-large-v3-turbo"
    tts = factory.build_tts(cfg)
    assert isinstance(tts, CachingTTS) and isinstance(tts._inner, FallbackTTS)
    assert isinstance(factory.build_stt(cfg), FallbackSTT)


def test_fallback_can_be_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TTS_KIND", "openai_compatible")
    monkeypatch.setenv("AISKRA_AI_ALLOW_EXTERNAL", "true")
    monkeypatch.setenv("TTS_FALLBACK_MODEL", "")
    assert load_ai_config(CONFIG).tts.fallback is None
