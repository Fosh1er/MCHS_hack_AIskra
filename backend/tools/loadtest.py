"""Нагрузочный тест АИскры (п. 6.1, ТЗ «Производительность»).

Что меряется:
1. Вход 100 пользователей (по 20 одновременно).
2. Смешанная нагрузка: 100 обучающихся за АРМ; из них 20 ведут «активные сессии» — учебный вызов, разговор
   с ИИ-заявителем, карточка 112, сохранение, работа ДДС; остальные 80 — журналы, карточки, справочники с паузами
   «на чтение» 1–3 с. Цель ТЗ: отклик ≤2 с (p95).
3. Пропускная способность записи: 20 одновременных писателей открывают карточки (запись карточки и аудита) —
   цель ≥100 операций в секунду.
4. Отчёт по занятию с 20 участниками: «оценить все» + отчёт — цель ≤30 с.

Подготовка стенда (учётки load001…load100 и teacher, пароль — AISKRA_DEMO_PASSWORD):
    AISKRA_DEMO_PASSWORD=… uv run python -m aiskra.cli demo-seed --load-users 100
Запуск:
    AISKRA_DEMO_PASSWORD=… uv run python tools/loadtest.py --base http://127.0.0.1:8000 --duration 60
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

API = "/api/v1"
FIRE_FLAT = "1050001"  # пожар в квартире — как в тестах карточки 112
SERVICES = ["S101", "S103", "S102", "CEMP"]


def card_data(aon: str) -> dict[str, Any]:
    return {
        "phones": {"aon": aon, "provided": "", "on_site": "", "foreign": False},
        "channel": "mts",
        "applicant": {"name": "Иванов Иван", "status": "witness", "foreign_language": False},
        "victims": {"has": True, "count": 2},
        "card_types": ["101"],
        "incident_types": [FIRE_FLAT],
        "questionnaire": {"101": {"Признаки происшествия": "жилой дом", "Уточнение": "открытое пламя"}},
        "card_flags": ["victims"],
        "address": {"street": "Новая Басманная улица", "house": "6", "okrug": "CAO", "district": "basmannyy"},
        "description": "Горит квартира на третьем этаже, из окна идёт дым, на лестнице люди",
    }


@dataclass
class Stats:
    samples: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    errors: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def table(self) -> list[dict[str, Any]]:
        rows = []
        for name, xs in sorted(self.samples.items()):
            xs = sorted(xs)
            q = statistics.quantiles(xs, n=100) if len(xs) >= 2 else [xs[0]] * 99
            rows.append(
                {
                    "op": name,
                    "n": len(xs),
                    "errors": self.errors.get(name, 0),
                    "p50_ms": round(q[49] * 1000),
                    "p95_ms": round(q[94] * 1000),
                    "p99_ms": round(q[98] * 1000),
                    "max_ms": round(xs[-1] * 1000),
                }
            )
        for name, n in self.errors.items():
            if name not in self.samples:
                rows.append(
                    {"op": name, "n": 0, "errors": n, "p50_ms": None, "p95_ms": None, "p99_ms": None, "max_ms": None}
                )
        return rows


async def timed(stats: Stats, name: str, coro: Any) -> httpx.Response | None:
    t = time.perf_counter()
    try:
        r: httpx.Response = await coro
    except httpx.HTTPError:
        stats.errors[name] += 1
        return None
    stats.samples[name].append(time.perf_counter() - t)
    if r.status_code >= 400:
        stats.errors[name] += 1
    return r


async def login(base: str, user: str, password: str, stats: Stats) -> httpx.AsyncClient:
    c = httpx.AsyncClient(base_url=base, timeout=30)
    r = await timed(
        stats,
        "POST /auth/login",
        c.post(f"{API}/auth/login", json={"login": user, "password": password, "arm_number": "1"}),
    )
    if r is None or r.status_code != 200:
        raise SystemExit(f"Не удалось войти {user}: {r.status_code if r else 'сеть'} {r.text[:200] if r else ''}")
    return c


async def reader(c: httpx.AsyncClient, stats: Stats, until: float, rng: random.Random) -> None:
    """Обучающийся просматривает журналы, карточки и справочники с паузами «на чтение»."""
    card_ids: list[str] = []
    while time.monotonic() < until:
        op = rng.random()
        if op < 0.35:
            r = await timed(
                stats, "GET /incidents/journal", c.get(f"{API}/incidents/journal", params={"page_size": 15})
            )
            if r is not None and r.status_code == 200:
                card_ids = [x["id"] for x in r.json()["items"]][:5] or card_ids
        elif op < 0.55:
            svc = rng.choice(SERVICES)
            await timed(
                stats,
                "GET /incidents/dds/{svc}/journal",
                c.get(f"{API}/incidents/dds/{svc}/journal", params={"page_size": 10}),
            )
        elif op < 0.7 and card_ids:
            await timed(stats, "GET /incidents/cards/{id}", c.get(f"{API}/incidents/cards/{rng.choice(card_ids)}"))
        elif op < 0.8:
            await timed(stats, "GET /dictionaries/card-types", c.get(f"{API}/dictionaries/card-types"))
        elif op < 0.88:
            await timed(stats, "GET /dictionaries/services", c.get(f"{API}/dictionaries/services"))
        elif op < 0.94:
            await timed(
                stats,
                "GET /dictionaries/addresses/suggest",
                c.get(
                    f"{API}/dictionaries/addresses/suggest",
                    params={"q": rng.choice(["тверская 1", "новая басманная", "ленинский 30", "арбат"])},
                ),
            )
        else:
            await timed(stats, "GET /training/sessions/my", c.get(f"{API}/training/sessions/my"))
        await asyncio.sleep(rng.uniform(1, 3))


async def operator(
    c: httpx.AsyncClient, stats: Stats, until: float, rng: random.Random, session_id: str | None
) -> None:
    """Активная сессия: вызов → разговор → карточка → сохранение → работа ДДС по своей карточке."""
    while time.monotonic() < until:
        r = await timed(
            stats, "POST /training/calls/incoming", c.post(f"{API}/training/calls/incoming", json={"groups": [1]})
        )
        if r is None or not r.is_success:
            await asyncio.sleep(1)
            continue
        call = r.json()
        r = await timed(
            stats,
            "POST /incidents/cards",
            c.post(
                f"{API}/incidents/cards",
                json={"aon": call["aon"], "scenario_id": call["scenario_id"], "session_id": session_id},
            ),
        )
        if r is None or not r.is_success:
            await asyncio.sleep(1)
            continue
        card = r.json()
        await timed(
            stats,
            "POST /training/calls/{id}/answer",
            c.post(f"{API}/training/calls/{call['call_id']}/answer", json={"card_id": card["id"]}),
        )
        for q in ("Что случилось?", "Назовите адрес", "Есть пострадавшие?"):
            await asyncio.sleep(rng.uniform(0.5, 1.0))
            await timed(
                stats,
                "POST /training/calls/{id}/replicas",
                c.post(f"{API}/training/calls/{call['call_id']}/replicas", json={"text": q}),
            )
        r = await timed(
            stats,
            "GET /dictionaries/services/resolve",
            c.get(
                f"{API}/dictionaries/services/resolve",
                params={"incident_type": FIRE_FLAT, "flag": "victims", "district": "basmannyy"},
            ),
        )
        services = [
            {"code": s["code"], "is_main": s["main"], "added_by": "auto"}
            for s in (r.json()["services"] if r is not None and r.status_code == 200 else [])
        ]
        await timed(
            stats,
            "POST /incidents/cards/{id}/save",
            c.post(
                f"{API}/incidents/cards/{card['id']}/save", json={"data": card_data(call["aon"]), "services": services}
            ),
        )
        await timed(stats, "POST /training/calls/{id}/end", c.post(f"{API}/training/calls/{call['call_id']}/end"))
        base = f"{API}/incidents/dds/S101/cards/{card['id']}"
        await timed(stats, "POST /incidents/dds/.../received", c.post(f"{base}/received"))
        await timed(
            stats,
            "POST /incidents/dds/.../status",
            c.post(f"{base}/status", json={"status": "accepted", "order_no": "1", "comment": "выслан расчёт"}),
        )
        await asyncio.sleep(rng.uniform(0.5, 1.5))


async def writers(clients: list[httpx.AsyncClient], seconds: float) -> tuple[int, int, float]:
    """Сколько карточек (запись карточки + аудит) база принимает в секунду при 20 одновременных писателях."""
    done = errors = 0
    until = time.monotonic() + seconds

    async def one(c: httpx.AsyncClient) -> None:
        nonlocal done, errors
        while time.monotonic() < until:
            try:
                r = await c.post(f"{API}/incidents/cards", json={"aon": "+7 (900) 000-00-00"})
                done += r.is_success
                errors += not r.is_success
            except httpx.HTTPError:
                errors += 1

    t = time.monotonic()
    await asyncio.gather(*(one(c) for c in clients))
    return done, errors, time.monotonic() - t


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--users", type=int, default=100)
    ap.add_argument("--sessions", type=int, default=20, help="активных сессий (вызов → карточка → ДДС)")
    ap.add_argument("--duration", type=float, default=60, help="секунд смешанной нагрузки")
    ap.add_argument("--write-seconds", type=float, default=15)
    ap.add_argument("--out", default="loadtest-result.json")
    args = ap.parse_args()
    password = os.environ.get("AISKRA_DEMO_PASSWORD") or ""
    if not password:
        raise SystemExit("Задайте AISKRA_DEMO_PASSWORD (пароль учёток load001…, teacher)")
    stats = Stats()

    # 1. вход по 20 одновременно
    sem = asyncio.Semaphore(20)

    async def enter(i: int) -> httpx.AsyncClient:
        async with sem:
            return await login(args.base, f"load{i:03d}", password, stats)

    t0 = time.perf_counter()
    clients = await asyncio.gather(*(enter(i) for i in range(1, args.users + 1)))
    login_s = time.perf_counter() - t0
    teacher = await login(args.base, "teacher", password, Stats())

    # занятие для отчёта: 20 активных — операторы 112
    active = clients[: args.sessions]
    ids = {u["login"]: u["id"] for u in (await teacher.get(f"{API}/training/students")).json()}
    body = {
        "title": f"Нагрузочный тест {time.strftime('%H:%M:%S')}",
        "mode": "cards_112",
        "groups": [1],
        "participants": [{"student_id": ids[f"load{i:03d}"], "role": "112"} for i in range(1, args.sessions + 1)],
    }
    session_id = (await teacher.post(f"{API}/training/sessions", json=body)).json()["id"]
    await teacher.post(f"{API}/training/sessions/{session_id}/start")

    # 2. смешанная нагрузка
    until = time.monotonic() + args.duration
    tasks = [operator(c, stats, until, random.Random(i), session_id) for i, c in enumerate(active)]
    tasks += [reader(c, stats, until, random.Random(1000 + i)) for i, c in enumerate(clients[args.sessions :])]
    t1 = time.perf_counter()
    await asyncio.gather(*tasks)
    mixed_s = time.perf_counter() - t1
    total_requests = sum(len(v) for k, v in stats.samples.items() if k != "POST /auth/login")

    # 3. запись
    done, werr, wsec = await writers(active, args.write_seconds)

    # 4. отчёт по занятию
    await teacher.post(f"{API}/training/sessions/{session_id}/finish")
    t2 = time.perf_counter()
    ev = await teacher.post(f"{API}/assessment/sessions/{session_id}/evaluate", timeout=120)
    rep = await teacher.get(f"{API}/assessment/sessions/{session_id}/report", timeout=120)
    report_s = time.perf_counter() - t2

    rows = stats.table()
    reading = [x for k, v in stats.samples.items() if k != "POST /auth/login" for x in v]
    reading.sort()
    p95_all = statistics.quantiles(reading, n=100)[94] if len(reading) > 1 else 0
    result = {
        "users": args.users,
        "active_sessions": args.sessions,
        "duration_s": round(mixed_s, 1),
        "login_all_s": round(login_s, 2),
        "requests": total_requests,
        "rps": round(total_requests / mixed_s, 1),
        "p95_all_ms": round(p95_all * 1000),
        "errors": sum(v for k, v in stats.errors.items()),
        "write_ops_per_s": round(done / wsec, 1),
        "write_errors": werr,
        "report": {
            "evaluated": ev.json() if ev.status_code == 200 else ev.text[:200],
            "cards": rep.json().get("cards_count") if rep.status_code == 200 else None,
            "seconds": round(report_s, 2),
        },
        "ops": rows,
    }
    for c in [*clients, teacher]:
        await c.aclose()
    await asyncio.to_thread(Path(args.out).write_text, json.dumps(result, ensure_ascii=False, indent=2), "utf-8")

    print(f"\nВход {args.users} пользователей: {result['login_all_s']} с")
    print(
        f"Смешанная нагрузка {result['duration_s']} с: {result['requests']} запросов, {result['rps']} в секунду, "
        f"p95 всех — {result['p95_all_ms']} мс, ошибок — {result['errors']}"
    )
    print(f"{'операция':44} {'n':>6} {'ош':>4} {'p50':>6} {'p95':>6} {'p99':>6} {'max':>6}")
    for r in rows:
        cells = [r[k] if r[k] is not None else "-" for k in ("p50_ms", "p95_ms", "p99_ms", "max_ms")]
        print(f"{r['op']:44} {r['n']:>6} {r['errors']:>4} " + " ".join(f"{x:>6}" for x in cells))
    print(f"Запись: {result['write_ops_per_s']} карточек/с (ошибок {werr})")
    rep_ = result["report"]
    print(f"Отчёт по занятию ({rep_['cards']} карточек): {rep_['seconds']} с — {rep_['evaluated']}")


if __name__ == "__main__":
    asyncio.run(main())
