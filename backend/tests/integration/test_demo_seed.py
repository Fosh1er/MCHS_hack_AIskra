"""Стенд одной командой (M6, F5): на чистой базе demo-seed создаёт и обычные, и ветвящиеся сценарии.

Найдено e2e-набором (F6.5): сценарий без ветвления хранит в `scenarios.branching` JSON `null`, проверка
`IS NOT NULL` принимала обычные сценарии за ветвящиеся — на чистой базе ветвящихся не появлялось."""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import select

from aiskra.demo_seed import seed
from aiskra.modules.training.infrastructure.branch_catalog import YamlBranchCatalog
from aiskra.modules.training.infrastructure.models import ScenarioModel
from aiskra.platform.db import create_engine, create_session_factory
from aiskra.platform.settings import Settings
from tests.integration.conftest import create_schema, make_settings


async def _branching(settings: Settings) -> list[object]:
    engine = create_engine(settings.database_url)
    try:
        async with create_session_factory(engine)() as s:
            return list((await s.execute(select(ScenarioModel.branching))).scalars())
    finally:
        await engine.dispose()


def test_seed_on_clean_db_creates_branching_scenarios(tmp_path: Path) -> None:
    settings = make_settings(tmp_path / "seed.db")
    create_schema(settings.database_url)
    templates = len(YamlBranchCatalog(settings.dictionaries_dir / "branch_templates.yaml").templates())

    asyncio.run(seed(settings, password="Seed-Pass-2026", scenarios=2, materials_dir=None))
    snapshots = asyncio.run(_branching(settings))
    assert sum(1 for b in snapshots if b) == templates
    assert len(snapshots) == 2 + templates

    asyncio.run(seed(settings, password="Seed-Pass-2026", scenarios=2, materials_dir=None))  # повтор — без дублей
    assert len(asyncio.run(_branching(settings))) == 2 + templates
