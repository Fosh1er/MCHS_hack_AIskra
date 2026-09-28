"""Пауза учебного таймера на время подсказок по экрану (п. 5.3): таймер карточки 112 и таймер решения ДДС.

Новичок при первом открытии экрана читает подсказки; это время не должно идти в норматив. Пауз может быть
несколько (подсказки реестра ДДС, затем карточки), но всего не больше MAX_TIMER_PAUSE на таймер — иначе пауза
стала бы лазейкой «остановить время». Длительность каждой паузы команды пишут в журнал аудита.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from aiskra.shared.errors import DomainError

MAX_TIMER_PAUSE = timedelta(minutes=10)
_MAX_MS = int(MAX_TIMER_PAUSE.total_seconds() * 1000)


def start_pause(paused_ms: int | None, started_at: datetime | None, now: datetime) -> datetime:
    """Начало паузы. Уже на паузе — та же пауза (повтор запроса после сбоя связи)."""
    if started_at is not None:
        return started_at
    if (paused_ms or 0) >= _MAX_MS:
        raise DomainError("Таймер уже стоял на паузе 10 минут — больше нельзя", code="timer_pause_used")
    return now


def end_pause(paused_ms: int | None, started_at: datetime | None, now: datetime) -> int:
    """Конец паузы: сколько всего таймер стоял, мс, не больше MAX_TIMER_PAUSE. Паузы нет — прежнее значение."""
    if started_at is None:
        return paused_ms or 0
    pause = max(0, int((now - started_at).total_seconds() * 1000))
    return min((paused_ms or 0) + pause, _MAX_MS)
