"""Резервная копия не останавливает API (F6.6): сериализация и разбор — в потоке, не в цикле событий.

Нагрузочный тест на PostgreSQL нашёл паузу 8–10 с у всех запросов через минуту после старта: ежедневная копия
(`daily_backup_loop`) делала json.dump и gzip всех таблиц прямо в цикле событий единственного процесса API.
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

from aiskra.modules.identity.infrastructure.models import UserModel
from aiskra.platform import backup
from aiskra.platform.backup import FileBackupStore
from aiskra.platform.db import create_engine, create_session_factory
from aiskra.platform.models_registry import metadata


@pytest.fixture
async def engine(tmp_path: Path) -> Any:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'backup.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    async with create_session_factory(engine)() as s:
        for i in range(50):
            s.add(UserModel(id=uuid.uuid4(), login=f"user{i:02d}", full_name=f"Пользователь {i}", role="student"))
        await s.commit()
    yield engine
    await engine.dispose()


async def test_backup_serializes_off_event_loop_and_round_trips(
    engine: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    threads: dict[str, bool] = {}
    write, read = backup._write, backup._read

    def slow_write(*args: Any) -> int:
        threads["write_in_loop_thread"] = threading.current_thread() is threading.main_thread()
        time.sleep(0.3)  # «большая база»: цикл событий в это время должен жить
        return write(*args)

    def spy_read(*args: Any) -> Any:
        threads["read_in_loop_thread"] = threading.current_thread() is threading.main_thread()
        return read(*args)

    monkeypatch.setattr(backup, "_write", slow_write)
    monkeypatch.setattr(backup, "_read", spy_read)
    store = FileBackupStore(engine, tmp_path / "backups")

    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    task = asyncio.create_task(ticker())
    info = await store.create()
    task.cancel()

    assert threads == {"write_in_loop_thread": False}
    assert ticks >= 5  # пока копия писалась, другие задачи цикла выполнялись
    assert info.rows >= 50 and info.tables > 0

    restored = await store.restore(info.name)
    assert threads["read_in_loop_thread"] is False
    assert restored.rows == info.rows
