"""Кольцевой буфер последних записей лога (п. 5.2, «логи» в панели администратора). Без файлов и внешних
систем: последние 2000 записей процесса в памяти."""

from __future__ import annotations

import logging
from collections import deque
from datetime import UTC, datetime

from aiskra.modules.system.application.ports.admin import LogRecord

_ORDER = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


class RingBufferHandler(logging.Handler):
    def __init__(self, capacity: int = 2000) -> None:
        super().__init__(level=logging.INFO)
        self.records: deque[LogRecord] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
            if record.exc_info and record.exc_info[0] is not None:
                msg += f" [{record.exc_info[0].__name__}: {record.exc_info[1]}]"
            self.records.append(
                LogRecord(
                    at=datetime.fromtimestamp(record.created, UTC),
                    level=record.levelname,
                    logger=record.name,
                    message=msg[:2000],
                )
            )
        except Exception:
            self.handleError(record)

    def recent(self, *, level: str, limit: int, q: str) -> list[LogRecord]:
        floor = _ORDER.get(level, 20)
        needle = q.lower()
        out = [
            r
            for r in reversed(self.records)
            if _ORDER.get(r.level, 20) >= floor and (not needle or needle in r.message.lower() or needle in r.logger)
        ]
        return out[:limit]


_handler: RingBufferHandler | None = None


def install() -> RingBufferHandler:
    """Подключить буфер к корневому логгеру (один раз на процесс)."""
    global _handler
    if _handler is None:
        _handler = RingBufferHandler()
        logging.getLogger().addHandler(_handler)
        if logging.getLogger().level > logging.INFO or logging.getLogger().level == logging.NOTSET:
            logging.getLogger().setLevel(logging.INFO)
    return _handler
