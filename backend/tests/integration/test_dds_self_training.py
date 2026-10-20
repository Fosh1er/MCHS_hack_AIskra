"""Самостоятельная тренировка ДДС (п. 2.1, рекомендация экспертов п. 10): вне занятия обучающийся сам получает
учебную карточку своей службы — её видит только он; решение оценивается сразу, с рекомендациями."""

import asyncio
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from aiskra.cli import create_user
from aiskra.main import create_app
from aiskra.shared.security import Role
from tests.integration.conftest import PASSWORD, create_schema, login, make_settings, seed_users
from tests.integration.test_journal import as_user, start_lesson

URL = "/api/v1/training/self-training/dds"


@pytest.fixture(scope="module")
def app_client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Callable[[], TestClient]]:
    settings = make_settings(Path(tmp_path_factory.mktemp("db")) / "self_training.db")
    create_schema(settings.database_url)
    seed_users(settings)
    for login_, name in (("petrov", "Петров Пётр"), ("sidorov", "Сидоров Семён")):
        asyncio.run(
            create_user(
                settings, login=login_, full_name=name, role=Role.STUDENT, password=PASSWORD, operator_number="9"
            )
        )
    app = create_app(settings)
    with TestClient(app) as first:
        login(first, "admin")
        assert first.post("/api/v1/dictionaries/import").status_code == 200
        yield lambda: TestClient(app)


def journal_ids(c: TestClient, service: str) -> set[str]:
    r = c.get(f"/api/v1/incidents/dds/{service}/journal", params={"page_size": 100})
    assert r.status_code == 200, r.text
    return {row["id"] for row in r.json()["items"]}


def status(c: TestClient, service: str, card_id: str, st: str, order_no: str = "", comment: str = "") -> Any:
    return c.post(
        f"/api/v1/incidents/dds/{service}/cards/{card_id}/status",
        json={"status": st, "order_no": order_no, "comment": comment},
    )


def test_empty_bank_generates_card_on_the_fly(app_client: Callable[[], TestClient]) -> None:
    sidorov = as_user(app_client, "sidorov")
    r = sidorov.post(URL, json={"service_code": "DDS_BASMANNYY"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["generated"] is True and body["waiting"] == 1
    view = sidorov.get(f"/api/v1/incidents/dds/DDS_BASMANNYY/cards/{body['card_id']}").json()
    assert view["self_training"] is True and view["service_status"] == "added"
    assert status(sidorov, "DDS_BASMANNYY", body["card_id"], "rejected", comment="не наш район").status_code == 200


def test_self_training_card_private_limited_and_assessed(app_client: Callable[[], TestClient]) -> None:
    teacher, petrov, sidorov = (as_user(app_client, u) for u in ("teacher", "petrov", "sidorov"))
    ids = teacher.post("/api/v1/training/scenarios/generate", json={"count": 3, "groups": [1]}).json()["ids"]
    for sid in ids:
        assert teacher.post(f"/api/v1/training/scenarios/{sid}/approve").status_code == 200
    scenario = teacher.get(f"/api/v1/training/scenarios/{ids[0]}").json()
    service = scenario["reference_card"]["services"][0]["code"]

    assert teacher.post(URL, json={"service_code": service}).status_code == 403  # нет права training.participate
    assert petrov.post(URL, json={"service_code": "NO_SUCH"}).status_code == 404

    r = petrov.post(URL, json={"service_code": service})
    assert r.status_code == 201, r.text
    issued = r.json()
    card_id = issued["card_id"]
    assert issued["generated"] is False and issued["waiting"] == 1
    approved = [teacher.get(f"/api/v1/training/scenarios/{i}").json() for i in ids]
    with_service = {s["id"] for s in approved if service in {x["code"] for x in s["reference_card"]["services"]}}
    assert issued["scenario_id"] in with_service  # из банка — сценарий, где служба в эталоне

    # видит только сам обучающийся (и преподаватель); другому — «не поступала»
    assert card_id in journal_ids(petrov, service)
    view = petrov.get(f"/api/v1/incidents/dds/{service}/cards/{card_id}").json()
    assert view["self_training"] is True and view["next_statuses"] == ["accepted", "rejected"]
    assert card_id not in journal_ids(sidorov, service)
    assert sidorov.get(f"/api/v1/incidents/dds/{service}/cards/{card_id}").status_code == 404
    assert sidorov.post(f"/api/v1/incidents/dds/{service}/cards/{card_id}/received").status_code == 404
    assert status(sidorov, service, card_id, "accepted", "1", "чужая").status_code == 404
    assert card_id in journal_ids(teacher, service)
    # в журнал 112 обучающегося учебная карточка ДДС не попадает: это не его работа оператором
    rows = petrov.get("/api/v1/incidents/journal", params={"page_size": 100}).json()["items"]
    assert card_id not in {row["id"] for row in rows}

    # предел — 3 ожидающих решения
    assert petrov.post(URL, json={"service_code": service}).status_code == 201
    assert petrov.post(URL, json={"service_code": service}).json()["waiting"] == 3
    full = petrov.post(URL, json={"service_code": service})
    assert full.status_code == 422 and full.json()["error"] == "self_queue_full"

    # решение до «Работы завершены» — оценка без преподавателя, с рекомендациями
    assert petrov.post(f"/api/v1/incidents/dds/{service}/cards/{card_id}/received").status_code == 200
    assert status(petrov, service, card_id, "accepted", "17", "Выслан наряд").status_code == 200
    for st in ("response_started", "arrived", "works_in_progress", "works_completed"):
        assert status(petrov, service, card_id, st, comment="работы ведутся").status_code == 200
    a = petrov.post(f"/api/v1/assessment/cards/{card_id}/evaluate", json={"role": "dds", "service_code": service})
    assert a.status_code == 200, a.text
    details = a.json()["details"]
    assert details["has_reference"] is True and details["role"] == "dds"
    recs = details["recommendations"]
    assert recs and all(r["text"] for r in recs)  # без звонков старшему — совет по звонкам
    assert sidorov.post(
        f"/api/v1/assessment/cards/{card_id}/evaluate", json={"role": "dds", "service_code": service}
    ).status_code in (403, 404)
    progress = petrov.get("/api/v1/assessment/my/progress").json()
    assert progress["recommendations"] and progress["points"][-1]["role"] == "dds"  # кабинет обучающегося

    # решение принято — место в очереди освободилось
    assert petrov.post(URL, json={"service_code": service}).status_code == 201

    # на занятии карточки даёт занятие — самостоятельная тренировка недоступна
    start_lesson(app_client, dds={"sidorov": service}, operators=("student",))
    blocked = sidorov.post(URL, json={"service_code": service})
    assert blocked.status_code == 422 and blocked.json()["error"] == "in_session"
