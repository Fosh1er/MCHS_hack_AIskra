"""Запись звонка одним файлом (п. 8.7 ТЗ: аудио в MP3/WAV): склейка озвученных реплик.

WAV склеивается по отсчётам: формат — по первой реплике, остальные приводятся к нему (моно/стерео, частота — простой
пересчёт отсчётов), между репликами — пауза тишины. MP3 склеивается по кадрам (без теговых блоков ID3 внутри) —
так делают и плееры при последовательной записи; паузу в MP3 без перекодирования не вставить.
Только стандартная библиотека: ffmpeg в образе нет.
"""

from __future__ import annotations

import array
import io
import sys
import wave
from dataclasses import dataclass

from aiskra.shared.errors import DomainError

GAP_MS = 450  # пауза между репликами: как смена говорящего в трубке


@dataclass(frozen=True)
class Pcm:
    channels: int
    rate: int
    samples: array.array[int]  # 16 бит со знаком, каналы чередуются


def audio_format(blob: bytes) -> str | None:
    if blob[:4] == b"RIFF" and blob[8:12] == b"WAVE":
        return "wav"
    if blob[:3] == b"ID3" or (len(blob) > 1 and blob[0] == 0xFF and blob[1] & 0xE0 == 0xE0):
        return "mp3"
    return None


def _read_wav(blob: bytes) -> Pcm:
    try:
        with wave.open(io.BytesIO(blob), "rb") as w:
            if w.getsampwidth() != 2:
                raise DomainError("Синтез отдал WAV не 16 бит — склейка не поддерживается", code="audio_format")
            frames = w.readframes(w.getnframes())
            channels, rate = w.getnchannels(), w.getframerate()
    except (wave.Error, EOFError) as e:
        raise DomainError("Синтез отдал повреждённый WAV", code="audio_format") from e
    samples = array.array("h")
    samples.frombytes(frames[: len(frames) // 2 * 2])
    if sys.byteorder == "big":
        samples.byteswap()
    return Pcm(channels, rate, samples)


def _convert(p: Pcm, channels: int, rate: int) -> array.array[int]:
    s = p.samples
    if p.channels != channels:
        if p.channels == 2 and channels == 1:
            s = array.array("h", ((s[i] + s[i + 1]) // 2 for i in range(0, len(s) - 1, 2)))
        elif p.channels == 1 and channels == 2:
            s = array.array("h", (v for v in s for _ in (0, 1)))
        else:
            raise DomainError("Реплики звонка в несовместимых форматах звука", code="audio_format")
    if p.rate != rate:
        frames = len(s) // channels
        n = frames * rate // p.rate
        s = array.array("h", (s[(i * p.rate // rate) * channels + c] for i in range(n) for c in range(channels)))
    return s


def join_wav(segments: list[bytes], gap_ms: int = GAP_MS) -> bytes:
    if not segments:
        raise DomainError("В звонке нет реплик", code="empty_call")
    first = _read_wav(segments[0])
    channels, rate = first.channels, first.rate
    gap = array.array("h", bytes(2 * channels * (rate * gap_ms // 1000)))
    out = array.array("h")
    for i, blob in enumerate(segments):
        if i:
            out.extend(gap)
        out.extend(first.samples if i == 0 else _convert(_read_wav(blob), channels, rate))
    if sys.byteorder == "big":
        out.byteswap()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(out.tobytes())
    return buf.getvalue()


def _strip_id3(blob: bytes) -> bytes:
    if blob[:3] == b"ID3" and len(blob) >= 10:
        size = (blob[6] << 21) | (blob[7] << 14) | (blob[8] << 7) | blob[9]
        blob = blob[10 + size + (10 if blob[5] & 0x10 else 0) :]
    if len(blob) >= 128 and blob[-128:-125] == b"TAG":
        blob = blob[:-128]
    return blob


def join_mp3(segments: list[bytes]) -> bytes:
    if not segments:
        raise DomainError("В звонке нет реплик", code="empty_call")
    return b"".join(_strip_id3(s) for s in segments)


def join_call_audio(segments: list[bytes]) -> tuple[bytes, str]:
    """Склеить реплики в один файл; формат — тот, что отдаёт синтез: `(звук, "wav" | "mp3")`."""
    formats = {audio_format(s) for s in segments}
    if formats == {"wav"}:
        return join_wav(segments), "wav"
    if formats == {"mp3"}:
        return join_mp3(segments), "mp3"
    raise DomainError("Синтез отдал звук, который не склеить в один файл (нужен WAV или MP3)", code="audio_format")
