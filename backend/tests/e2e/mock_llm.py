"""Локальная модель-заглушка с OpenAI-протоколом для e2e (F6.5): только стандартная библиотека, без сети наружу.

Отдаёт то, что тренажёр ждёт от OpenRouter или локального сервера:
- `POST /v1/chat/completions` — без `stream` одним ответом, со `stream: true` — SSE `data: {choices[0].delta}` по
  словам с задержкой (видно промежуточное состояние «ИИ генерирует»), затем `[DONE]`. Если в запросе есть схема
  («Отвечай строго JSON по схеме: …», её вставляет адаптер), ответ — валидный JSON по этой схеме;
- `POST /v1/audio/speech` — WAV (тон 440 Гц), в любом `response_format` (e2e задаёт `TTS_FORMAT=wav`);
- `POST /v1/audio/transcriptions` — фиксированный текст `STT_TEXT`;
- `GET /v1/models` — одна модель.

Состояние для проверок — `MockLLM.requests` (путь, поток, модель). Отказы: `stop()` — порт закрыт, как у упавшего
сервера; `fail_tts = True` — синтез отвечает 503.

    python tests/e2e/mock_llm.py --port 8900     # вручную: DEMO_LLM_URL=http://127.0.0.1:8900/v1
"""

from __future__ import annotations

import argparse
import io
import json
import math
import struct
import threading
import time
import wave
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

MODEL = "e2e-mock"
REPLY = "Помогите, у нас пожар! Дым идёт из окна кухни. Мы на пятом этаже, пожалуйста, приезжайте быстрее."
JSON_TEXT = "Тестовый ответ модели-заглушки."
STT_TEXT = "Что у вас случилось?"
SCHEMA_MARK = "Отвечай строго JSON по схеме:\n"
# Голосовой полигон просит начинать ответ технической строкой тональности (frontend/public/voice-lab/app.js)
TONE_MARK = "Каждый ответ начинай ровно с одной технической строки"
TONE_LINE = ("TONE|emotion=fear|intensity=7|pace=fast|volume=loud|urgency=high|trust=4|cooperation=6|breathing=rapid"
             "|interruptions=none\n")  # fmt: skip


def example(schema: dict[str, Any], defs: dict[str, Any]) -> Any:
    """Валидный пример по JSON Schema (pydantic): строки — осмысленный текст в пределах maxLength, списки пустые."""
    if "$ref" in schema:
        return example(defs[schema["$ref"].split("/")[-1]], defs)
    if "default" in schema:
        return schema["default"]
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    for key in ("anyOf", "oneOf"):
        if key in schema:
            options = [s for s in schema[key] if s.get("type") != "null"] or schema[key]
            return example(options[0], defs)
    if "allOf" in schema:
        return example(schema["allOf"][0], defs)
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        return {name: example(sub, defs) for name, sub in schema.get("properties", {}).items()}
    if kind == "array":
        return []
    if kind in ("integer", "number"):
        low, high = schema.get("minimum", 0), schema.get("maximum")
        value = (low + high) / 2 if high is not None else low
        return int(value) if kind == "integer" else float(value)
    if kind == "boolean":
        return False
    if kind == "null":
        return None
    return JSON_TEXT[: int(schema.get("maxLength", len(JSON_TEXT)))]


def json_answer(messages: list[dict[str, Any]]) -> str | None:
    """Схема из системного сообщения адаптера → JSON-ответ; нет схемы — None (обычный текст)."""
    for m in messages:
        content = m.get("content")
        if isinstance(content, str) and content.startswith(SCHEMA_MARK):
            schema = json.loads(content[len(SCHEMA_MARK) :])
            return json.dumps(example(schema, schema.get("$defs", {})), ensure_ascii=False)
    return None


def tone_wav(seconds: float = 0.4, rate: int = 24_000, *, silence_before: float = 0, silence_after: float = 0) -> bytes:
    """Тон 440 Гц в WAV: ответ синтеза и «речь» для синтетического микрофона браузера (паузы — для VAD)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * silence_before))
        frames = (int(12000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(int(rate * seconds)))
        w.writeframes(b"".join(struct.pack("<h", f) for f in frames))
        w.writeframes(b"\x00\x00" * int(rate * silence_after))
    return buf.getvalue()


@dataclass
class Seen:
    path: str
    stream: bool = False
    model: str = ""
    at: float = field(default_factory=time.time)


class MockLLM:
    """Сервер-заглушка в потоке текущего процесса. Перезапуск на том же порту — `stop()` и `start()`."""

    def __init__(self, port: int = 0, *, token_delay: float = 0.12) -> None:
        self.port = port
        self.token_delay = token_delay
        self.fail_tts = False
        self.requests: list[Seen] = []
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def count(self, path: str) -> int:
        return sum(1 for r in self.requests if r.path.endswith(path))

    def start(self) -> MockLLM:
        mock = self

        class Handler(_Handler):
            owner = mock

        ThreadingHTTPServer.allow_reuse_address = True
        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, name="mock-llm", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    @property
    def running(self) -> bool:
        return self._server is not None


class _Handler(BaseHTTPRequestHandler):
    owner: MockLLM
    server_version = "e2e-mock/1.0"

    def log_message(self, format: str, *args: Any) -> None:  # тихо: вывод сервера мешает отчёту pytest
        return

    def _body(self) -> bytes:
        size = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(size) if size else b""

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data: Any) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode(), "application/json")

    def do_GET(self) -> None:
        self.owner.requests.append(Seen(self.path))
        if self.path.rstrip("/").endswith("/models"):
            self._json(200, {"object": "list", "data": [{"id": MODEL, "object": "model"}]})
        else:
            self._json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:
        raw = self._body()
        path = self.path.rstrip("/")
        if path.endswith("/chat/completions"):
            body = json.loads(raw or b"{}")
            stream = bool(body.get("stream"))
            self.owner.requests.append(Seen(path, stream, str(body.get("model") or "")))
            messages = body.get("messages") or []
            tone = any(TONE_MARK in str(m.get("content")) for m in messages if m.get("role") == "system")
            text = json_answer(messages) or (TONE_LINE + REPLY if tone else REPLY)
            if stream:
                self._stream(text)
            else:
                choice = {"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
                usage = {"prompt_tokens": 10, "completion_tokens": len(text.split())}
                self._json(
                    200,
                    {"id": "mock", "object": "chat.completion", "model": MODEL, "choices": [choice], "usage": usage},
                )
        elif path.endswith("/audio/speech"):
            self.owner.requests.append(Seen(path))
            if self.owner.fail_tts:
                self._json(503, {"error": {"message": "tts down"}})
            else:
                self._send(200, tone_wav(), "audio/wav")
        elif path.endswith("/audio/transcriptions"):
            self.owner.requests.append(Seen(path))
            self._json(200, {"text": STT_TEXT})
        else:
            self._json(404, {"error": {"message": "not found"}})

    def _stream(self, text: str) -> None:
        """SSE без Content-Length: поток закрывается вместе с соединением (HTTP/1.0)."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def event(delta: dict[str, Any], finish: str | None = None) -> None:
            chunk = {"id": "mock", "object": "chat.completion.chunk", "model": MODEL,
                     "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}  # fmt: skip
            self.wfile.write(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()

        try:
            event({"role": "assistant"})
            words = text.split(" ")
            for i, word in enumerate(words):
                time.sleep(self.owner.token_delay)
                event({"content": word + (" " if i < len(words) - 1 else "")})
            event({}, "stop")
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # клиент оборвал поток (перебивание) — это не ошибка заглушки


def main() -> None:
    ap = argparse.ArgumentParser(description="модель-заглушка с OpenAI-протоколом")
    ap.add_argument("--port", type=int, default=8900)
    ap.add_argument("--delay", type=float, default=0.12, help="пауза между словами потока, с")
    args = ap.parse_args()
    mock = MockLLM(args.port, token_delay=args.delay).start()
    print(f"Заглушка модели: {mock.url}", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        mock.stop()


if __name__ == "__main__":
    main()
