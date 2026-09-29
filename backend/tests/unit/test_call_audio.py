"""П. 8.7: запись звонка одним файлом — склейка WAV с паузами и приведением формата, склейка MP3 по кадрам."""

import io
import wave

import pytest

from aiskra.modules.training.domain.audio import audio_format, join_call_audio, join_wav
from aiskra.shared.errors import DomainError


def wav(seconds: float, rate: int = 16_000, channels: int = 1, value: int = 1000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(value.to_bytes(2, "little", signed=True) * channels * int(rate * seconds))
    return buf.getvalue()


def info(blob: bytes) -> tuple[int, int, float]:
    with wave.open(io.BytesIO(blob), "rb") as w:
        return w.getnchannels(), w.getframerate(), w.getnframes() / w.getframerate()


def test_wav_segments_joined_with_gaps() -> None:
    out = join_wav([wav(1.0), wav(0.5)], gap_ms=500)
    assert info(out) == (1, 16_000, 2.0)


def test_other_rate_and_channels_converted_to_first() -> None:
    out, ext = join_call_audio([wav(1.0, rate=24_000), wav(1.0, rate=16_000, channels=2)])
    channels, rate, seconds = info(out)
    assert ext == "wav" and (channels, rate) == (1, 24_000) and seconds == pytest.approx(2.45, abs=0.01)


def test_mp3_frames_concatenated_without_inner_tags() -> None:
    frame = b"\xff\xfb\x90\x00" + b"\x00" * 100
    tagged = b"ID3\x04\x00\x00\x00\x00\x00\x05" + b"x" * 5 + frame
    out, ext = join_call_audio([tagged, tagged])
    assert ext == "mp3" and out == frame + frame and audio_format(out) == "mp3"


def test_mixed_or_unknown_format_refused() -> None:
    with pytest.raises(DomainError):
        join_call_audio([wav(0.1), b"\xff\xfb\x90\x00"])
    with pytest.raises(DomainError):
        join_call_audio([b"OggS...."])
