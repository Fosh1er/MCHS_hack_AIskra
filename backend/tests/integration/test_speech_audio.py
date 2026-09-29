"""П. 3.6, V2 через HTTP: звук реплики собеседника — права как у просмотра звонка, подача по состоянию заявителя,
без настроенного синтеза — честный отказ (интерфейс озвучит браузером)."""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from aiskra.ai.ports import AudioBlob, VoiceProfile
from tests.integration.test_journal import app_client as journal_app_client  # noqa: F401
from tests.integration.test_journal import as_user


@pytest.fixture(scope="module")
def app_client(journal_app_client: Callable[[], TestClient]) -> Iterator[Callable[[], TestClient]]:  # noqa: F811
    yield journal_app_client


class RecordingTTS:
    enabled = True
    model_id = "stub-tts"

    def __init__(self) -> None:
        self.calls: list[tuple[str, VoiceProfile]] = []

    async def synthesize(self, text: str, *, voice: VoiceProfile) -> AudioBlob:
        self.calls.append((text, voice))
        return AudioBlob(content=b"RIFF-stub-audio", mime="audio/wav")


def test_replica_audio(app_client: Callable[[], TestClient]) -> None:
    student = as_user(app_client, "student")
    call = student.post("/api/v1/training/calls/incoming", json={}).json()
    cid = call["call_id"]
    opening = student.post(f"/api/v1/training/calls/{cid}/answer", json={}).json()
    rude = student.post(f"/api/v1/training/calls/{cid}/replicas", json={"text": "Успокойтесь! Быстрее!"}).json()
    audio = f"/api/v1/training/calls/{cid}/messages/{rude['message_id']}/audio"

    assert student.get("/api/v1/training/speech").json() == {"enabled": False, "tts": False}
    off = student.get(audio)
    assert off.status_code == 422 and off.json()["error"] == "tts_disabled"  # интерфейс озвучит браузером

    services = student.app.state.services  # type: ignore[attr-defined]
    real, stub = services.tts, RecordingTTS()
    services.tts = stub
    try:
        assert student.get("/api/v1/training/speech").json()["tts"] is True
        r = student.get(audio)
        assert r.status_code == 200 and r.headers["content-type"] == "audio/wav" and r.content == b"RIFF-stub-audio"
        text, profile = stub.calls[-1]
        assert text == rude["text"]  # в синтез уходит только текст реплики
        assert profile.voice in {"applicant_female", "applicant_male", "applicant"}
        assert profile.emotion == rude["tone"]["emotion"] and profile.style and "caller" in profile.style
        assert profile.speed == {"slow": 0.9, "normal": 1.0, "fast": 1.15, "very_fast": 1.3}[rude["tone"]["pace"]]

        view = student.get(f"/api/v1/training/calls/{cid}").json()
        operator_id = next(m["id"] for m in view["messages"] if m["speaker"] == "operator")
        assert student.get(f"/api/v1/training/calls/{cid}/messages/{operator_id}/audio").status_code == 404
        assert student.get(f"/api/v1/training/calls/{cid}/messages/{opening['message_id']}/audio").status_code == 200

        assert as_user(app_client, "petrov").get(audio).status_code == 404  # чужой звонок
        assert as_user(app_client, "teacher").get(audio).status_code == 200  # преподаватель слышит любой
        assert TestClient(student.app).get(audio).status_code == 401  # без входа
    finally:
        services.tts = real


def test_call_recording_wav(app_client: Callable[[], TestClient]) -> None:
    """П. 8.7: запись звонка одним WAV — реплики оператора и заявителя по порядку, оператор — голос «operator»."""
    import io
    import wave

    def tone_wav(n: int) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(8000)
            w.writeframes(b"\x10\x00" * n)
        return buf.getvalue()

    class WavTTS(RecordingTTS):
        async def synthesize(self, text: str, *, voice: VoiceProfile) -> AudioBlob:
            self.calls.append((text, voice))
            return AudioBlob(content=tone_wav(800), mime="audio/wav")

    student = as_user(app_client, "student")
    cid = student.post("/api/v1/training/calls/incoming", json={}).json()["call_id"]
    student.post(f"/api/v1/training/calls/{cid}/answer", json={})
    student.post(f"/api/v1/training/calls/{cid}/replicas", json={"text": "Служба 112, что случилось?"})
    url = f"/api/v1/training/calls/{cid}/recording"

    off = student.get(url)
    assert off.status_code == 422 and off.json()["error"] == "tts_disabled"
    services = student.app.state.services  # type: ignore[attr-defined]
    real, stub = services.tts, WavTTS()
    services.tts = stub
    try:
        r = student.get(url)
        assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
        assert "attachment" in r.headers["content-disposition"] and ".wav" in r.headers["content-disposition"]
        with wave.open(io.BytesIO(r.content), "rb") as w:
            n = len(stub.calls)
            assert n >= 3 and w.getnframes() == 800 * n + 8000 * 450 // 1000 * (n - 1)
        voices = [p.voice for _, p in stub.calls]
        assert "operator" in voices and any(v.startswith("applicant") for v in voices)
        assert as_user(app_client, "teacher").get(url).status_code == 200  # преподаватель видит любой звонок
        assert as_user(app_client, "petrov").get(url).status_code == 404  # чужой звонок
    finally:
        services.tts = real
