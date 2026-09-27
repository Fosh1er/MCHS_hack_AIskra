"""Предзаполненная история для демо-стенда (п. 7.4): прошедшие занятия группы «Смена 1 (демо)» за последние
две недели — чтобы аналитика, допуск, прогресс и отчёты на показе были содержательными.

Занятия проводятся через API приложения (в том же процессе) под демо-учётками: учебный вызов, опрос заявителя,
карточка, отработка ДДС, звонок старшему группы. Ошибки обучающихся — из каталога бенчмарка п. 3.5, их частота
падает от занятия к занятию (кривая обучения). Затем время занятий, карточек и статусов сдвигается на прошлые дни
с реалистичной длительностью (запись идёт за секунды), и только после этого занятия оцениваются.

Данные синтетические и помечены в названии занятий. Запускать после `demo-seed`:

    AISKRA_DATABASE_URL=… AISKRA_DEMO_PASSWORD=… uv run python tools/demo_history.py --lessons 6
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select, update

import aiskra.platform.models_registry  # noqa: F401  — все ORM-модели
from aiskra.main import create_app
from aiskra.modules.assessment.domain.validation import MUTATIONS_112, Attempt112
from aiskra.modules.assessment.infrastructure.models import AssessmentModel
from aiskra.modules.identity.infrastructure.models import UserModel
from aiskra.modules.incidents.infrastructure.models import CardServiceModel, CardServiceStatusModel, IncidentCardModel
from aiskra.modules.training.infrastructure.models import TrainingSessionModel
from aiskra.platform.db import create_engine
from aiskra.platform.settings import Settings

API = "/api/v1"
# ошибки, которые безопасно вносить через API (коды типов и служб остаются существующими)
SAFE = {"no_main_service", "no_secondary_service", "wrong_house", "no_district", "missed_flag", "wrong_street",
        "missed_victims", "victims_count", "no_victims_question"}  # fmt: skip
MUTATIONS = {m.key: m for m in MUTATIONS_112 if m.key in SAFE}
# профиль обучающегося: вероятность ошибки на первом и последнем занятии, время карточки (с), время решения ДДС (с)
PROFILES = {
    "op1": {"err": (0.5, 0.12), "time": (50, 85, 38, 68)},
    "op2": {"err": (0.95, 0.55), "time": (70, 120, 55, 88)},
    "dds1": {"err": (0.45, 0.1), "react": (14, 36, 8, 24)},
    "dds2": {"err": (0.7, 0.35), "react": (20, 55, 12, 38)},
}
DDS = {"dds1": "S101", "dds2": "S103"}


def client(app: Any, login: str, password: str, arm: str) -> TestClient:
    c = TestClient(app)
    r = c.post(f"{API}/auth/login", json={"login": login, "password": password, "arm_number": arm})
    if r.status_code != 200:
        raise SystemExit(f"Вход {login}: {r.status_code} {r.text} — сначала demo-seed с тем же AISKRA_DEMO_PASSWORD")
    return c


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def card_data(ref: dict[str, Any], aon: str) -> dict[str, Any]:
    a = ref["address"]
    return {
        "phones": {"aon": aon},
        "channel": "mts",
        "applicant": {**ref["applicant"], "foreign_language": False},
        "victims": ref["victims"],
        "card_types": ref["card_types"],
        "incident_types": ref["incident_types"],
        "questionnaire": ref["questionnaire"],
        "card_flags": ref["card_flags"],
        "address": {k: a.get(k) or "" for k in ("street", "house", "building", "structure", "okrug", "district")},
        "description": " ".join(ref["description_keywords"]) + ". Заявитель сообщает о происшествии.",
    }


def operator_card(op: TestClient, teacher: TestClient, session_id: str, groups: list[int], p_err: float,
                  rng: random.Random) -> dict[str, Any]:  # fmt: skip
    call = op.post(f"{API}/training/calls/incoming", json={"groups": groups}).json()
    ref = teacher.get(f"{API}/training/scenarios/{call['scenario_id']}").json()["reference_card"]
    card = op.post(
        f"{API}/incidents/cards",
        json={"aon": call["aon"], "scenario_id": call["scenario_id"], "session_id": session_id},
    ).json()
    op.post(f"{API}/training/calls/{call['call_id']}/answer", json={"card_id": card["id"]})
    attempt = Attempt112(card_data(ref, call["aon"]), [s["code"] for s in ref["services"]])
    applied = []
    for _ in range(3):  # до трёх ошибок в карточке
        if rng.random() < p_err:
            m = MUTATIONS[rng.choice(sorted(MUTATIONS))]
            mutated = m.apply(attempt, ref)
            if mutated is not None:
                attempt, applied = mutated, [*applied, m.key]
            p_err *= 0.6
    for q in ("Что случилось?", "Назовите адрес", "Есть пострадавшие?"):
        if q == "Есть пострадавшие?" and "no_victims_question" in applied:
            continue
        op.post(f"{API}/training/calls/{call['call_id']}/replicas", json={"text": q})
    services = [{"code": c, "is_main": c == attempt.services[0], "added_by": "auto"} for c in attempt.services]
    r = op.post(f"{API}/incidents/cards/{card['id']}/save", json={"data": attempt.data, "services": services})
    if r.status_code != 200:  # ошибка не прошла проверку формы — сохраняем без неё
        attempt = Attempt112(card_data(ref, call["aon"]), [s["code"] for s in ref["services"]])
        services = [{"code": c, "is_main": s.get("main", False), "added_by": "auto"} for c, s in
                    zip(attempt.services, ref["services"], strict=True)]  # fmt: skip
        r = op.post(f"{API}/incidents/cards/{card['id']}/save", json={"data": attempt.data, "services": services})
        r.raise_for_status()
    op.post(f"{API}/training/calls/{call['call_id']}/end")
    return {"id": card["id"], "services": attempt.services}


def dds_work(dds: TestClient, service: str, card_id: str, p_err: float, rng: random.Random) -> None:
    base = f"{API}/incidents/dds/{service}/cards/{card_id}"
    if dds.post(f"{base}/received").status_code != 200:
        return
    order = None if rng.random() < p_err * 0.5 else str(rng.randint(10, 99))

    def comment(text: str) -> str | None:
        return None if rng.random() < p_err * 0.5 else text

    r = dds.post(f"{base}/status", json={"status": "accepted", "order_no": order, "comment": comment("Выслан наряд")})
    if r.status_code != 200:  # служба требует номер наряда при «Принята» — без него статус не ставится
        dds.post(f"{base}/status", json={"status": "accepted", "order_no": "15", "comment": comment("Выслан наряд")})
    chain = [("response_started", "Наряд выехал"), ("arrived", "Прибыли на место"),
             ("works_in_progress", "Работы начаты"), ("works_completed", "Работы завершены")]  # fmt: skip
    stop = len(chain) if rng.random() > p_err * 0.6 else rng.randint(1, len(chain) - 1)
    for status, text in chain[:stop]:
        dds.post(f"{base}/status", json={"status": status, "comment": comment(text)})
    if rng.random() > p_err * 0.5:
        call = dds.post(
            f"{API}/training/calls/dds", json={"card_id": card_id, "service_code": service, "party": "brigade"}
        )
        if call.status_code == 200:
            dds.post(f"{API}/training/calls/{call.json()['call_id']}/replicas", json={"text": "Доложите обстановку"})
            dds.post(f"{API}/training/calls/{call.json()['call_id']}/end")


async def backdate(url: str, session_id: str, start: datetime, rng: random.Random, t: float) -> None:
    """Сдвиг занятия в прошлое: реалистичная длительность карточек и время решений ДДС."""
    engine = create_engine(url)
    sid = uuid.UUID(session_id)
    async with engine.begin() as conn:
        cards = (
            await conn.execute(
                select(IncidentCardModel.id, IncidentCardModel.author_id)
                .where(IncidentCardModel.session_id == sid)
                .order_by(IncidentCardModel.opened_at)
            )
        ).all()
        authors = {row.author_id for row in cards}
        logins = dict(
            (await conn.execute(select(UserModel.id, UserModel.login).where(UserModel.id.in_(authors)))).all()
        )
        clock = start
        for cid, author in cards:
            prof = PROFILES.get(logins.get(author, ""), PROFILES["op1"])["time"]
            secs = rng.uniform(lerp(prof[0], prof[2], t), lerp(prof[1], prof[3], t))
            opened, saved = clock, clock + timedelta(seconds=secs)
            await conn.execute(
                update(IncidentCardModel)
                .where(IncidentCardModel.id == cid)
                .values(opened_at=opened, saved_at=saved, processing_ms=int(secs * 1000))
            )
            await conn.execute(
                update(CardServiceModel).where(CardServiceModel.card_id == cid).values(card_saved_at=saved)
            )
            statuses = (
                await conn.execute(
                    select(
                        CardServiceStatusModel.id, CardServiceStatusModel.service_code, CardServiceStatusModel.status
                    )
                    .where(CardServiceStatusModel.card_id == cid)
                    .order_by(CardServiceStatusModel.id)
                )
            ).all()
            step: dict[str, datetime] = {}
            for st_id, code, status in statuses:
                dds_login = next((k for k, v in DDS.items() if v == code), "dds1")
                react = PROFILES[dds_login]["react"]
                if status in ("added", "received"):
                    at = saved + timedelta(seconds=1 if status == "added" else 4)
                elif code not in step:
                    at = saved + timedelta(
                        seconds=rng.uniform(lerp(react[0], react[2], t), lerp(react[1], react[3], t))
                    )
                else:
                    at = step[code] + timedelta(minutes=rng.uniform(4, 12))
                if status not in ("added", "received"):
                    step[code] = at
                await conn.execute(
                    update(CardServiceStatusModel).where(CardServiceStatusModel.id == st_id).values(at=at)
                )
            clock = saved + timedelta(minutes=rng.uniform(2, 5))
        await conn.execute(
            update(TrainingSessionModel)
            .where(TrainingSessionModel.id == sid)
            .values(
                started_at=start - timedelta(minutes=2),
                finished_at=clock + timedelta(minutes=5),
                created_at=start - timedelta(days=1),
            )
        )  # fmt: skip
    await engine.dispose()


async def backdate_assessments(url: str, since: datetime) -> None:
    """Оценка — через час после сохранения карточки (прогресс обучающегося строится по дате оценки)."""
    engine = create_engine(url)
    async with engine.begin() as conn:
        rows = (
            await conn.execute(
                select(AssessmentModel.id, IncidentCardModel.saved_at)
                .join(IncidentCardModel, IncidentCardModel.id == AssessmentModel.card_id)
                .where(AssessmentModel.created_at >= since)
            )
        ).all()
        for aid, saved in rows:
            if saved is not None:
                await conn.execute(
                    update(AssessmentModel)
                    .where(AssessmentModel.id == aid)
                    .values(created_at=saved + timedelta(hours=1))
                )
    await engine.dispose()  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lessons", type=int, default=6)
    ap.add_argument("--cards", type=int, default=4, help="карточек на оператора за занятие")
    ap.add_argument("--seed", type=int, default=112)
    args = ap.parse_args()
    password = os.environ.get("AISKRA_DEMO_PASSWORD")
    if not password:
        raise SystemExit("Задайте AISKRA_DEMO_PASSWORD — тот же, что для demo-seed")
    # запросы идут внутри процесса по http — Secure-cookie стенда с TLS здесь не нужна
    settings = Settings().model_copy(update={"session_cookie_secure": False})
    rng = random.Random(args.seed)
    app = create_app(settings)
    began = datetime.now(UTC)
    with TestClient(app):
        teacher = client(app, "teacher", password, "")
        users = {u: client(app, u, password, str(i + 1)) for i, u in enumerate(PROFILES)}
        people = {s["login"]: s["id"] for s in teacher.get(f"{API}/training/students").json()}
        today = datetime.now(UTC).replace(hour=7, minute=0, second=0, microsecond=0)  # 10:00 МСК
        days = [round(14 - i * 12 / max(1, args.lessons - 1)) for i in range(args.lessons)]  # 14 … 2 дня назад
        topics = [[1], [1, 22], [22], [1, 15], [15, 17], [1, 22, 17], [14, 16], [1, 22]]
        made = []
        for n, day in enumerate(days):
            t = n / max(1, args.lessons - 1)
            groups = topics[n % len(topics)]
            body = {
                "title": f"Смена 1 (демо-история): занятие {n + 1}",
                "mode": "mixed",
                "card_source": "trainee",
                "groups": groups,
                "participants": [
                    {"student_id": people["op1"], "role": "112"},
                    {"student_id": people["op2"], "role": "112"},
                    {"student_id": people["dds1"], "role": "dds", "dds_service_code": DDS["dds1"]},
                    {"student_id": people["dds2"], "role": "dds", "dds_service_code": DDS["dds2"]},
                ],
                "settings": {"difficulty": 2 + (n * 2) // args.lessons},
            }
            sid = teacher.post(f"{API}/training/sessions", json=body).json()["id"]
            teacher.post(f"{API}/training/sessions/{sid}/start")
            for _ in range(args.cards):
                for op in ("op1", "op2"):
                    card = operator_card(users[op], teacher, sid, groups, lerp(*PROFILES[op]["err"], t), rng)
                    for dds_login, service in DDS.items():
                        if service in card["services"]:
                            dds_work(users[dds_login], service, card["id"], lerp(*PROFILES[dds_login]["err"], t), rng)
            teacher.post(f"{API}/training/sessions/{sid}/finish")
            asyncio.run(backdate(settings.database_url, sid, today - timedelta(days=day), rng, t))
            made.append(sid)
            print(f"Занятие {n + 1}: {day} дн. назад, группы {groups}", flush=True)
        for sid in made:
            r = teacher.post(f"{API}/assessment/sessions/{sid}/evaluate").json()
            print(f"  оценено {r['assessed']}, пропущено {r['skipped']}", flush=True)
    asyncio.run(backdate_assessments(settings.database_url, began - timedelta(minutes=1)))
    print(f"История готова: {len(made)} занятий.")


if __name__ == "__main__":
    main()
