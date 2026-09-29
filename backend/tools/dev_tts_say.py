"""Заглушка синтеза речи для разработки на macOS (п. 3.6): OpenAI-совместимый `POST /v1/audio/speech` поверх
системной команды `say` и русского голоса Milena. Нужна, чтобы проверить серверную озвучку без ключа OpenRouter
и без Docker со Speaches.

Как Piper в изолированном контуре, эмоцию передаёт только темпом (`speed`); голос один на все роли. Слушает
только 127.0.0.1. Не для стенда и не для контура заказчика.

    make dev-tts          # или: cd backend && uv run python tools/dev_tts_say.py [--port 8100]
    # сервер тренажёра: TTS_KIND=openai_compatible TTS_URL=http://localhost:8100/v1 TTS_FORMAT=wav
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VOICE = "Milena"  # русский голос macOS: say -v '?' | grep ru_RU
BASE_RATE = 185  # слов в минуту при speed = 1.0
MAX_CHARS = 1000


def synthesize(text: str, speed: float) -> bytes:
    rate = int(BASE_RATE * min(max(speed, 0.5), 2.0))
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "speech.wav"
        subprocess.run(
            ["say", "-v", VOICE, "-r", str(rate), "--data-format=LEI16@24000", "-o", str(out), text[:MAX_CHARS]],
            check=True,
            timeout=30,
        )
        return out.read_bytes()


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, body: object) -> None:
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/v1/models":
            self._json(200, {"data": [{"id": f"macos-say-{VOICE.lower()}", "object": "model"}]})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/v1/audio/speech":
            self._json(404, {"error": "not found"})
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            text = str(body.get("input") or "").strip()
            if not text:
                self._json(400, {"error": "input is required"})
                return
            audio = synthesize(text, float(body.get("speed") or 1.0))
        except (ValueError, subprocess.SubprocessError) as exc:
            self._json(500, {"error": str(exc)})
            return
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(audio)))
        self.end_headers()
        self.wfile.write(audio)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", type=int, default=8100)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Синтез речи (say, {VOICE}): http://127.0.0.1:{args.port}/v1 — Ctrl+C, чтобы остановить", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
