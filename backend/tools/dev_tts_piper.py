"""Локальный синтез речи нейроголосами Piper (п. 3.6): OpenAI-совместимый `POST /v1/audio/speech` без Docker и ключей.
Те же голоса, что у Speaches в контуре заказчика, — тот же протокол и тот же адаптер `OpenAICompatibleTTS`, меняется
только `TTS_URL`. У каждой роли свой голос: `voice` в запросе — имя голоса (irina, denis, dmitri).

Движок — sherpa-onnx (Apache-2.0), а не пакет piper-tts (GPL-3.0). Модели Piper в int8 (~21 МБ каждая) скачиваются
при первом запуске в ~/.cache/aiskra/piper. Лицензии голосов (карточки моделей rhasspy/piper-voices):
- denis, dmitri — CC0;
- irina — «Unknown» (датасет RHVoice): единственный женский голос, для проверки; в контур заказчика — после уточнения;
- ruslan — CC BY-NC-SA, некоммерческая: не используется.
Эмоцию Piper передаёт только темпом (`speed`), как в контуре заказчика. Слушает только 127.0.0.1.

    make dev-tts   # или: cd backend && uv run --with sherpa-onnx --with numpy python tools/dev_tts_piper.py
    # сервер тренажёра: TTS_KIND=openai_compatible TTS_URL=http://localhost:8100/v1 TTS_FORMAT=wav
    #   TTS_VOICE=irina TTS_VOICE_FEMALE=irina TTS_VOICE_MALE=denis TTS_VOICE_BRIGADE=dmitri TTS_VOICE_SERVICE=irina
"""

from __future__ import annotations

import argparse
import io
import json
import tarfile
import threading
import time
import urllib.request
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import sherpa_onnx

RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models"
CACHE = Path.home() / ".cache" / "aiskra" / "piper"
MAX_CHARS = 1000


def ensure_model(voice: str, precision: str) -> Path:
    """Модель голоса в кеше; нет — скачать архив sherpa-onnx и распаковать (один раз)."""
    suffix = "" if precision == "fp32" else f"-{precision}"
    name = f"vits-piper-ru_RU-{voice}-medium{suffix}"
    folder = CACHE / name
    if not (folder / "tokens.txt").exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        print(f"Скачиваю голос {voice} ({precision})…", flush=True)
        with urllib.request.urlopen(f"{RELEASES}/{name}.tar.bz2", timeout=300) as resp:
            data = resp.read()
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:bz2") as tar:
            tar.extractall(CACHE, filter="data")
    return folder


def load_voice(folder: Path, threads: int) -> sherpa_onnx.OfflineTts:
    onnx = next(folder.glob("*.onnx"))
    vits = sherpa_onnx.OfflineTtsVitsModelConfig(
        model=str(onnx), lexicon="", tokens=str(folder / "tokens.txt"), data_dir=str(folder / "espeak-ng-data")
    )
    config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(vits=vits, provider="cpu", num_threads=threads), max_num_sentences=1
    )
    return sherpa_onnx.OfflineTts(config)


def to_wav(samples: Any, rate: int) -> bytes:
    pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1, 1) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    voices: ClassVar[dict[str, sherpa_onnx.OfflineTts]] = {}
    default = ""
    lock = threading.Lock()

    def _json(self, code: int, body: object) -> None:
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/v1/models":
            self._json(200, {"data": [{"id": f"piper-ru_RU-{v}", "object": "model"} for v in self.voices]})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/v1/audio/speech":
            self._json(404, {"error": "not found"})
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            text = str(body.get("input") or "").strip()[:MAX_CHARS]
            if not text:
                self._json(400, {"error": "input is required"})
                return
            name = str(body.get("voice") or "")
            voice = name if name in self.voices else self.default
            speed = min(max(float(body.get("speed") or 1.0), 0.5), 2.0)
            started = time.perf_counter()
            with self.lock:
                audio = self.voices[voice].generate(text, sid=0, speed=speed)
            wav = to_wav(audio.samples, audio.sample_rate)
        except (ValueError, RuntimeError) as exc:
            self._json(500, {"error": str(exc)})
            return
        took = time.perf_counter() - started
        print(f"{time.strftime('%H:%M:%S')} {voice} ×{speed:.2f} за {took:.2f} с: «{text[:60]}»", flush=True)
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(wav)))
        self.end_headers()
        self.wfile.write(wav)

    def log_message(self, *args: Any) -> None:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--voices", default="irina,denis,dmitri", help="голоса через запятую; первый — по умолчанию")
    parser.add_argument("--precision", default="int8", choices=["int8", "fp16", "fp32"])
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    names = [v.strip() for v in args.voices.split(",") if v.strip()]
    Handler.voices = {v: load_voice(ensure_model(v, args.precision), args.threads) for v in names}
    Handler.default = names[0]
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    where = f"http://127.0.0.1:{args.port}/v1"
    print(f"Синтез речи (Piper: {', '.join(names)}): {where} — Ctrl+C, чтобы остановить", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
