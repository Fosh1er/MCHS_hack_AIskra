"""Номер карточки 112 при одновременном открытии на PostgreSQL (F6.6).

Нагрузочный тест на PostgreSQL в docker нашёл ошибку: 20 операторов одновременно получали один и тот же
«максимум + 1», вставка ждала чужой commit, и после 5 повторов `POST /incidents/cards` отвечал 500
(«Не удалось выделить номер карточки»). На SQLite ошибка не видна — один писатель.

Тест нужен PostgreSQL: переменная `AISKRA_TEST_POSTGRES_URL` (в CI — сервис postgres в job `checks`), например
`postgresql+asyncpg://postgres@localhost:5432/aiskra_test`. **Только пустая тестовая база: таблицы пересоздаются.**
Без переменной тест пропускается.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from aiskra.modules.identity.infrastructure.models import UserModel
from aiskra.modules.incidents.domain.incident import IncidentCard
from aiskra.modules.incidents.infrastructure.models import IncidentCardModel
from aiskra.modules.incidents.infrastructure.repositories import NUMBER_BASE, SqlCardRepository
from aiskra.platform.db import create_engine, create_session_factory
from aiskra.platform.models_registry import metadata

URL = os.environ.get("AISKRA_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not URL.startswith("postgresql"), reason="нужен PostgreSQL: AISKRA_TEST_POSTGRES_URL")

OPERATORS = 30  # больше, чем повторов выдачи номера, и больше пула соединений приложения не нужно


async def test_concurrent_cards_get_unique_sequential_numbers() -> None:
    engine = create_engine(URL)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.drop_all)
            await conn.run_sync(metadata.create_all)
        factory = create_session_factory(engine)
        author = uuid.uuid4()
        async with factory() as s:
            s.add(UserModel(id=author, login="pg-operator", full_name="Оператор Тестовый", role="student"))
            await s.commit()

        async def open_card() -> int:
            async with factory() as s:
                card = IncidentCard(author_id=author, opened_at=datetime.now(UTC))
                await SqlCardRepository(s).add(card)
                await asyncio.sleep(0.05)  # остальная транзакция открытия: запись аудита, commit
                await s.commit()
                return card.number

        # все открытия доводим до конца (иначе незавершённые транзакции мешают очистке базы)
        results = await asyncio.gather(*(open_card() for _ in range(OPERATORS)), return_exceptions=True)
        failed = [repr(r) for r in results if isinstance(r, BaseException)]
        assert not failed, f"не открылись {len(failed)} из {OPERATORS}: {failed[:3]}"
        numbers = [r for r in results if isinstance(r, int)]
        assert sorted(numbers) == list(range(NUMBER_BASE + 1, NUMBER_BASE + OPERATORS + 1))
        async with factory() as s:
            stored = (await s.execute(select(IncidentCardModel.number))).scalars().all()
        assert sorted(stored) == sorted(numbers)
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.drop_all)
        await engine.dispose()
