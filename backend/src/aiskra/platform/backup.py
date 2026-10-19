"""Логическая резервная копия рабочих данных (п. 5.2): все таблицы, кроме справочников (`dict_*`, их даёт импорт
из data/) и сессий входа. Формат — gzip JSON {format, created_at, tables: {имя: [строки]}}; типы восстанавливаются
по колонкам ORM-метаданных. Одинаково работает на PostgreSQL и SQLite.

Сериализация, сжатие и разбор копии — в отдельном потоке (`asyncio.to_thread`): на объёме года это секунды и десятки
секунд CPU. В цикле событий они останавливали весь API — ежедневная копия при старте стенда давала паузу 8–10 с у всех
запросов (нагрузочный тест на PostgreSQL, F6.6)."""

from __future__ import annotations

import asyncio
import base64
import gzip
import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import Date, DateTime, Integer, LargeBinary, Row, Table, Uuid, delete, insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from aiskra.modules.system.application.ports.admin import BackupInfo
from aiskra.platform.models_registry import metadata

FORMAT = "aiskra-backup/1"
SKIP_DUMP = {"auth_sessions"}
NAME = re.compile(r"^aiskra-\d{8}-\d{6}\.json\.gz$")


def _tables() -> list[Table]:
    return [t for t in metadata.sorted_tables if not t.name.startswith("dict_") and t.name not in SKIP_DUMP]


def _encode(v: Any) -> Any:
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, datetime | date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, bytes):
        return base64.b64encode(v).decode()
    raise TypeError(f"не сериализуется: {type(v).__name__}")


def _write(path: Path, created_at: datetime, rows: dict[str, list[Row[Any]]]) -> int:
    """Записать копию (в потоке, не в цикле событий). Возвращает число строк."""
    dump = {name: [dict(r._mapping) for r in table_rows] for name, table_rows in rows.items()}
    payload = {"format": FORMAT, "created_at": created_at.isoformat(), "tables": dump}
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, default=_encode)
    return sum(len(v) for v in dump.values())


def _read(path: Path, tables: list[Table]) -> dict[str, list[dict[str, Any]]]:
    """Прочитать и разобрать копию (в потоке): строки по таблицам с восстановленными типами."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        payload = json.load(f)
    if payload.get("format") != FORMAT:
        raise ValueError("Неизвестный формат копии")
    data: dict[str, list[dict[str, Any]]] = payload["tables"]
    return {t.name: [_decode(t, r) for r in data.get(t.name, [])] for t in tables}


def _decode(table: Table, row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, v in row.items():
        col = table.columns.get(name)
        if col is None:
            continue  # колонка удалена в новой схеме
        if v is not None:
            if isinstance(col.type, Uuid):
                v = UUID(v)
            elif isinstance(col.type, DateTime):
                v = datetime.fromisoformat(v)
            elif isinstance(col.type, Date):
                v = date.fromisoformat(v)
            elif isinstance(col.type, LargeBinary):
                v = base64.b64decode(v)
        out[name] = v
    return out


class FileBackupStore:
    def __init__(self, engine: AsyncEngine, directory: str | Path) -> None:
        self._engine = engine
        self._dir = Path(directory)

    def path(self, name: str) -> Path:
        if not NAME.match(name):
            raise FileNotFoundError(name)
        p = self._dir / name
        if not p.is_file():
            raise FileNotFoundError(name)
        return p

    def _info(self, p: Path, tables: int = 0, rows: int = 0) -> BackupInfo:
        st = p.stat()
        return BackupInfo(
            name=p.name,
            size_bytes=st.st_size,
            created_at=datetime.fromtimestamp(st.st_mtime, UTC),
            tables=tables,
            rows=rows,
        )

    async def create(self) -> BackupInfo:
        self._dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(UTC)
        raw: dict[str, list[Row[Any]]] = {}
        async with self._engine.connect() as conn:
            for t in _tables():
                raw[t.name] = list((await conn.execute(select(t))).all())
        name = f"aiskra-{now:%Y%m%d-%H%M%S}.json.gz"
        path = self._dir / name
        rows = await asyncio.to_thread(_write, path, now, raw)
        return self._info(path, len(raw), rows)

    def list(self) -> list[BackupInfo]:
        if not self._dir.is_dir():
            return []
        files = sorted((p for p in self._dir.iterdir() if NAME.match(p.name)), key=lambda p: p.name, reverse=True)
        return [self._info(p) for p in files]

    def prune(self, keep: int) -> int:
        old = self.list()[keep:]
        for b in old:
            (self._dir / b.name).unlink(missing_ok=True)
        return len(old)

    async def restore(self, name: str) -> BackupInfo:
        path = self.path(name)
        tables = _tables()
        data = await asyncio.to_thread(_read, path, tables)
        rows = 0
        async with self._engine.begin() as conn:
            # сессии входа ссылаются на пользователей — все выходят из системы
            await conn.execute(delete(metadata.tables["auth_sessions"]))
            for t in reversed(tables):
                await conn.execute(delete(t))
            for t in tables:
                batch = data[t.name]
                for i in range(0, len(batch), 500):
                    await conn.execute(insert(t), batch[i : i + 500])
                rows += len(batch)
            if conn.dialect.name == "postgresql":  # счётчики автоинкремента — после явных id
                q = conn.dialect.identifier_preparer.quote  # имена — из ORM-метаданных, но всё равно экранируем
                for t in tables:
                    for col in t.primary_key.columns:
                        if isinstance(col.type, Integer) and col.autoincrement is not False:
                            await conn.execute(
                                text(
                                    "SELECT setval(pg_get_serial_sequence(:t, :c), "
                                    f"COALESCE((SELECT MAX({q(col.name)}) FROM {q(t.name)}), 0) + 1, false)"
                                ),
                                {"t": t.name, "c": col.name},
                            )
        return self._info(path, len(tables), rows)
