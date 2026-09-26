"""Alembic (async). Метаданные — из aiskra.platform.models_registry, URL — из настроек."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from aiskra.platform.models_registry import metadata
from aiskra.platform.settings import Settings

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

URL = Settings().database_url


def run_offline() -> None:
    context.configure(url=URL, target_metadata=metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    engine = create_async_engine(URL)
    async with engine.connect() as conn:
        await conn.run_sync(_do_run)
    await engine.dispose()


if context.is_offline_mode():
    run_offline()
else:
    asyncio.run(run_online())
