"""События хода звонка для потокового ответа (F1, ADR-0013).

Обработчик реплики и движок профиля сообщают о ходе через приёмник `EventSink`; HTTP-слой превращает события
в SSE. Без приёмника (обычный запрос, тесты) логика та же — события просто никуда не уходят.

Виды событий:
- `model` — ответ пишет модель: `{task, model, provider}`; нет события — ответ по правилам (офлайн);
- `state` — состояние заявителя после реплики оператора, известно до генерации: `{tone, level_before, level_after,
  deltas}` (поля профиля — только при психологическом модификаторе);
- `token` — кусок ответа модели `{text}`;
- `replace` — ответ модели отклонён или модель сломалась посреди ответа: `{reason}`; итоговый текст придёт в `final`.
- `offline` — после `model` модель не ответила ни куском (недоступна): `{reason}`; ответ — по правилам.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

EventSink = Callable[[str, dict[str, Any]], Awaitable[None]]


async def emit(sink: EventSink | None, kind: str, data: dict[str, Any]) -> None:
    if sink is not None:
        await sink(kind, data)
