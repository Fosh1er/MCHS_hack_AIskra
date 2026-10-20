"""F3: звуки и волнение реплики заявителя для синтеза речи."""

from aiskra.modules.training.domain.voice_cues import agitation, sounds


def test_agitation_from_tension_or_eccs_level() -> None:
    assert [agitation(t) for t in (0, 3, 4, 6, 8, 10)] == [0, 0, 1, 2, 3, 3]
    assert [agitation(9, level) for level in (1, 2, 3, 4, 5)] == [0, 1, 2, 3, 3]  # профиль важнее напряжения
    assert agitation(6, intensity=1) == 1 and agitation(6, intensity=3) == 3 and agitation(0, intensity=1) == 0


def test_sounds_from_remarks_and_profile_voice() -> None:
    assert sounds("Алло", agitation=0, remarks=["плачет", "кладёт трубку"]) == ("sob",)
    assert sounds("Алло", agitation=3, profile_voice={"nonverbal": ["pant", "gasp", "sob"]}) == ("pant", "gasp")


def test_breath_only_when_agitated_and_nothing_else() -> None:
    assert sounds("Алло", agitation=2, breathing="irregular") == ("gasp",)
    assert sounds("Алло", agitation=1, breathing="irregular") == ()
    assert sounds("Алло", agitation=3, breathing="rapid", remarks=["плачет"]) == ("sob",)


def test_cough_when_caller_talks_about_smoke() -> None:
    assert sounds("Весь подъезд в дыму!", agitation=1) == ("cough",)
    assert sounds("Весь подъезд в дыму!", agitation=0) == ()
    assert sounds("Задыхаемся, дым!", agitation=3, breathing="irregular") == ("gasp", "cough")


async def test_replica_profile_takes_cues_from_psy_meta() -> None:
    """Звук реплики звонка с профилем: звуки — из `meta.voice`, волнение — по уровню ECCS, а не по напряжению."""
    from datetime import UTC, datetime
    from uuid import uuid4

    from aiskra.modules.training.application.speech import _Voices
    from aiskra.modules.training.domain.call import Call, CallMessage, CallParty, Speaker
    from aiskra.modules.training.domain.tone import initial_tone

    now = datetime.now(UTC)
    call = Call(student_id=uuid4(), role="112", party=CallParty.APPLICANT, direction="in", started_at=now)
    call.psy = {"intensity": 3}
    tone = initial_tone(1, 1).snapshot()  # спокойный по напряжению
    meta = {"remarks": ["плачет"], "voice": {"level": 3, "nonverbal": ["sob", "sniff"], "intensity": 3}}
    msg = CallMessage(call_id=uuid4(), speaker=Speaker.PARTY, text="Он не дышит", at=now, tone=tone, meta=meta)
    voices = _Voices(tts=None, calls=None, scenarios=None)  # type: ignore[arg-type]
    profile = await voices._profile(call, msg)
    assert profile.sounds == ("sob", "sniff") and profile.agitation == 3  # уровень 3 → 2, «ярко» → +1
    plain = CallMessage(call_id=uuid4(), speaker=Speaker.PARTY, text="Да", at=now, tone=tone)
    calm = await voices._profile(
        Call(student_id=uuid4(), role="112", party=CallParty.APPLICANT, direction="in", started_at=now), plain
    )
    assert calm.sounds == () and calm.agitation == 0
