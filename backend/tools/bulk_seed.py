"""Объём данных для нагрузочного теста (п. 6.1): N сохранённых карточек со службами и историей статусов
и M записей аудита — примерно год работы учебного центра. Только для стенда нагрузки, не для продакшена.

    AISKRA_DATABASE_URL=… uv run python tools/bulk_seed.py --cards 50000 --audit 200000
"""

from __future__ import annotations

import argparse
import asyncio
import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, insert, select

from aiskra.modules.audit.infrastructure.models import AuditLogModel
from aiskra.modules.identity.infrastructure.models import UserModel
from aiskra.modules.incidents.infrastructure.models import CardServiceModel, CardServiceStatusModel, IncidentCardModel
from aiskra.platform.db import create_engine
from aiskra.platform.settings import Settings

STREETS = ["Новая Басманная улица", "Тверская улица", "Ленинский проспект", "Арбат", "Профсоюзная улица"]
TYPES = [("101", "1050001"), ("103", "16010100"), ("102", "15010100"), ("104", "13010100")]
SERVICES = ["S101", "S102", "S103", "S104", "CEMP", "GORHOZ", "DDS_BASMANNYY", "PREF_CAO"]
CHAIN = ["added", "received", "accepted", "response_started", "arrived", "works_in_progress", "works_completed"]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", type=int, default=50_000)
    ap.add_argument("--audit", type=int, default=200_000)
    args = ap.parse_args()
    engine = create_engine(Settings().database_url)
    rng = random.Random(42)
    now = datetime.now(UTC)
    async with engine.begin() as conn:
        users = (await conn.execute(select(UserModel.id).where(UserModel.role == "student"))).scalars().all()
        start = (
            int(
                (await conn.execute(select(func.coalesce(func.max(IncidentCardModel.number), 36_000_000)))).scalar_one()
            )
            + 1
        )
        batch_c, batch_s, batch_h = [], [], []
        for i in range(args.cards):
            cid = uuid.uuid4()
            at = now - timedelta(minutes=rng.randint(0, 365 * 24 * 60))
            ct, it = rng.choice(TYPES)
            street = rng.choice(STREETS)
            batch_c.append(
                {
                    "id": cid,
                    "number": start + i,
                    "author_id": rng.choice(users),
                    "operator_number": str(rng.randint(100, 999)),
                    "arm_number": "1",
                    "origin": "student",
                    "channel": "mts",
                    "status": rng.choice(["registered", "worked", "checked"]),
                    "card_type_codes": [ct],
                    "incident_type_codes": [it],
                    "okrug_code": "CAO",
                    "district_code": "basmannyy",
                    "address_text": f"{street}, {rng.randint(1, 60)}",
                    "description": "Учебная карточка для нагрузочного теста",
                    "has_victims": rng.random() < 0.3,
                    "victims_count": 0,
                    "payload": {},
                    "opened_at": at,
                    "saved_at": at + timedelta(seconds=rng.randint(40, 200)),
                    "processing_ms": rng.randint(40_000, 200_000),
                    "search_key": f"{start + i} {street.lower()}",
                }
            )
            for j, code in enumerate(rng.sample(SERVICES, 3)):
                steps = CHAIN[: rng.randint(1, len(CHAIN))]
                batch_s.append(
                    {
                        "card_id": cid,
                        "service_code": code,
                        "is_main": j == 0,
                        "added_by": "auto",
                        "current_status": steps[-1],
                    }
                )
                for k, st in enumerate(steps):
                    batch_h.append(
                        {"card_id": cid, "service_code": code, "status": st, "at": at + timedelta(minutes=k)}
                    )
            if len(batch_c) >= 2_000:
                await conn.execute(insert(IncidentCardModel), batch_c)
                await conn.execute(insert(CardServiceModel), batch_s)
                await conn.execute(insert(CardServiceStatusModel), batch_h)
                batch_c, batch_s, batch_h = [], [], []
        if batch_c:
            await conn.execute(insert(IncidentCardModel), batch_c)
            await conn.execute(insert(CardServiceModel), batch_s)
            await conn.execute(insert(CardServiceStatusModel), batch_h)
        rows = []
        for _ in range(args.audit):
            rows.append(
                {
                    "at": now - timedelta(minutes=rng.randint(0, 365 * 24 * 60)),
                    "card_number": start + rng.randrange(max(args.cards, 1)),
                    "event": rng.choice(["card.created", "card.saved", "dds.status_changed", "auth.login_succeeded"]),
                    "description": "нагрузочный тест",
                    "actor_name": "Нагрузка",
                    "actor_login": "load001",
                }
            )
            if len(rows) >= 5_000:
                await conn.execute(insert(AuditLogModel), rows)
                rows = []
        if rows:
            await conn.execute(insert(AuditLogModel), rows)
    await engine.dispose()
    print(f"Добавлено: карточек {args.cards} (служб {args.cards * 3}), записей аудита {args.audit}")


if __name__ == "__main__":
    asyncio.run(main())
