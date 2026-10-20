"""Стенд одной командой (M6, F5): на чистой базе demo-seed создаёт и обычные, и ветвящиеся сценарии.

Найдено e2e-набором (F6.5): сценарий без ветвления хранит в `scenarios.branching` JSON `null`, проверка
`IS NOT NULL` принимала обычные сценарии за ветвящиеся — на чистой базе ветвящихся не появлялось."""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import select

from aiskra.demo_seed import DEMO_USERS, HOUSEHOLD, seed, seed_household
from aiskra.modules.dictionaries.infrastructure.models import IncidentTypeModel
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
    # случайный сценарий банка может попасть на строку `HOUSEHOLD` со службой в эталоне — тогда бытовой
    # не дублируется (seed_household идемпотентен), поэтому бытовых — от len(HOUSEHOLD) − 2 до len(HOUSEHOLD)
    assert 2 + templates + len(HOUSEHOLD) - 2 <= len(snapshots) <= 2 + templates + len(HOUSEHOLD)

    asyncio.run(seed(settings, password="Seed-Pass-2026", scenarios=2, materials_dir=None))  # повтор — без дублей
    assert len(asyncio.run(_branching(settings))) == len(snapshots)


async def _approved(settings: Settings) -> list[tuple[str | None, int | None, list[str]]]:
    engine = create_engine(settings.database_url)
    try:
        async with create_session_factory(engine)() as s:
            rows = (
                await s.execute(
                    select(ScenarioModel.incident_type_code, IncidentTypeModel.group_id, ScenarioModel.reference_card)
                    .outerjoin(IncidentTypeModel, IncidentTypeModel.code == ScenarioModel.incident_type_code)
                    .where(ScenarioModel.status == "approved")
                )
            ).all()
            return [(code, group, [x["code"] for x in ref.get("services", [])]) for code, group, ref in rows]
    finally:
        await engine.dispose()


def test_seed_household_scenarios_for_dds(tmp_path: Path) -> None:
    """Эксперты: ДДС — бытовые сценарии (животные, ЖКХ, экология). Не меньше 6 утверждённых, в эталоне каждого —
    служба демо-диспетчера (dds1 — S101, dds2 — S103); на работающем стенде `demo-seed --household` без дублей."""
    settings = make_settings(tmp_path / "household.db")
    create_schema(settings.database_url)
    asyncio.run(seed(settings, password="Seed-Pass-2026", scenarios=1, materials_dir=None))

    dds_services = {u.service for u in DEMO_USERS if u.service}
    household = [r for r in asyncio.run(_approved(settings)) if r[0] in {h.code for h in HOUSEHOLD}]
    assert len(household) >= 6
    assert {group for _, group, _ in household} == {8, 14, 21}
    for h in HOUSEHOLD:
        assert any(code == h.code and h.service in svc for code, _, svc in household), h
    assert all(dds_services & set(svc) for _, _, svc in household)
    for service in dds_services:  # обоим диспетчерам — свои карточки
        assert sum(1 for _, _, svc in household if service in svc) >= 3

    total = len(asyncio.run(_approved(settings)))
    assert asyncio.run(seed_household(settings)) == 0  # повтор на работающем стенде — без дублей
    asyncio.run(seed(settings, password="Seed-Pass-2026", scenarios=1, materials_dir=None))
    assert len(asyncio.run(_approved(settings))) == total
