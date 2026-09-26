"""SQLAlchemy 2 (async): движок, фабрика сессий, Unit of Work, базовый класс моделей."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, cast

from sqlalchemy import MetaData, Table, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Базовый класс ORM-моделей. ORM-модели живут в `modules/<m>/infrastructure`, не в домене."""

    metadata = MetaData(naming_convention=NAMING)


def create_engine(url: str) -> AsyncEngine:
    kwargs: dict[str, object] = {"pool_pre_ping": True}
    if url.startswith("postgresql"):
        kwargs.update(pool_size=10, max_overflow=10)
    return create_async_engine(url, **kwargs)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


class SqlAlchemyUnitOfWork:
    """Реализация порта UnitOfWork поверх сессии запроса."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


async def session_scope(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """Сессия на запрос: откат при исключении, закрытие всегда."""
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def ping(engine: AsyncEngine) -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def upsert(
    session: AsyncSession, model: type[Base], rows: Sequence[Mapping[str, Any]], keys: list[str], *, chunk: int = 400
) -> None:
    """Вставка с обновлением по естественному ключу. Поддерживает PostgreSQL и SQLite (тесты)."""
    if not rows:
        return
    bind = session.bind
    dialect = bind.dialect.name if bind is not None else "postgresql"
    if dialect not in {"postgresql", "sqlite"}:  # pragma: no cover
        raise RuntimeError(f"upsert не поддерживает диалект {dialect}")
    table = cast(Table, model.__table__)
    for start in range(0, len(rows), chunk):
        part = [dict(r) for r in rows[start : start + chunk]]
        stmt: Any = pg_insert(table) if dialect == "postgresql" else sqlite_insert(table)
        stmt = stmt.values(part)
        update = {c: stmt.excluded[c] for c in part[0] if c not in keys}
        stmt = (
            stmt.on_conflict_do_update(index_elements=keys, set_=update)
            if update
            else stmt.on_conflict_do_nothing(index_elements=keys)
        )
        await session.execute(stmt)
