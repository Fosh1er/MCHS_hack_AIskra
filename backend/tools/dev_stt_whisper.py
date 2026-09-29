"""Локальное распознавание речи для разработки и проверки (п. 1.4, 3.6): OpenAI-совместимый
`POST /v1/audio/transcriptions` поверх faster-whisper на процессоре — без Docker и без ключей.

Тот же протокол, что у Speaches и OpenRouter: сервер тренажёра ходит сюда тем же адаптером `OpenAICompatibleSTT`,
меняется только адрес (`STT_URL`). Модель скачивается с Hugging Face при первом запуске (small — около 480 МБ,
base — около 145 МБ) и занимает в памяти 0,5–0,7 ГБ (small, int8). Встроенный VAD faster-whisper отрезает тишину —
меньше «титров», которые Whisper сочиняет на шуме. Слушает только 127.0.0.1.

    make dev-stt   # или: cd backend && uv run --with faster-whisper python tools/dev_stt_whisper.py [--model base]
    # сервер тренажёра: STT_KIND=openai_compatible STT_URL=http://localhost:8200/v1
"""

from __future__ import annotations

import argparse
import io
import json
import threading
import time
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from faster_whisper import WhisperModel

MAX_BYTES = 25 * 1024 * 1024


def parse_multipart(content_type: str, body: bytes) -> dict[str, tuple[str | None, bytes]]:
    """multipart/form-data → {поле: (имя файла, байты)} стандартной библиотекой (модуль cgi удалён в Python 3.13)."""
    msg = BytesParser(policy=email_policy).parsebytes(f"Content-Type: {content_type}\r\n\r\n".encode() + body)
    out: dict[str, tuple[str | None, bytes]] = {}
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if isinstance(name, str):
            payload = part.get_payload(decode=True)
            out[name] = (part.get_filename(), payload if isinstance(payload, bytes) else b"")
    return out


class Handler(BaseHTTPRequestHandler):
    model: WhisperModel
    model_name: str
    lock = threading.Lock()  # одна модель — распознаём по одной фразе

    def _json(self, code: int, body: object) -> None:
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/v1/models":
            self._json(200, {"data": [{"id": self.model_name, "object": "model"}]})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/v1/audio/transcriptions":
            self._json(404, {"error": "not found"})
            return
        size = int(self.headers.get("Content-Length") or 0)
        if not 0 < size <= MAX_BYTES:
            self._json(413, {"error": "audio is empty or too large"})
            return
        fields = parse_multipart(self.headers.get("Content-Type", ""), self.rfile.read(size))
        audio = fields.get("file", (None, b""))[1]
        language = fields.get("language", (None, b"ru"))[1].decode() or "ru"
        if not audio:
            self._json(400, {"error": "file is required"})
            return
        started = time.perf_counter()
        try:
            with self.lock:
                segments, _ = self.model.transcribe(
                    io.BytesIO(audio),
                    language=language,
                    beam_size=1,
                    vad_filter=True,
                    condition_on_previous_text=False,
                )
                text = " ".join(s.text.strip() for s in segments).strip()
        except Exception as exc:  # любая ошибка декодирования или модели → 500 с причиной
            self._json(500, {"error": f"{exc.__class__.__name__}: {exc}"})
            return
        took = time.perf_counter() - started
        print(f"{time.strftime('%H:%M:%S')} {len(audio) // 1024} КБ → {took:.2f} с: «{text}»", flush=True)
        self._json(200, {"text": text})

    def log_message(self, *args: Any) -> None:  # запросы печатаем сами, одной строкой с результатом
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", default="small", help="tiny | base | small | medium | путь к модели CTranslate2")
    parser.add_argument("--port", type=int, default=8200)
    parser.add_argument("--threads", type=int, default=4, help="потоков процессора на распознавание")
    args = parser.parse_args()
    print(f"Загружаю faster-whisper «{args.model}» (первый запуск скачивает модель)…", flush=True)
    Handler.model = WhisperModel(args.model, device="cpu", compute_type="int8", cpu_threads=args.threads)
    Handler.model_name = f"faster-whisper-{args.model}"
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Распознавание речи: http://127.0.0.1:{args.port}/v1 — Ctrl+C, чтобы остановить", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
