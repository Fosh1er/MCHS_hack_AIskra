"""Переносимые типы колонок и преобразования: JSONB в PostgreSQL, JSON в SQLite (тесты)."""

from datetime import UTC, datetime

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

JsonType = JSON().with_variant(JSONB(), "postgresql")


def as_utc(value: datetime | None) -> datetime | None:
    """Время из БД — всегда aware UTC. SQLite теряет часовой пояс у `DateTime(timezone=True)`."""
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
