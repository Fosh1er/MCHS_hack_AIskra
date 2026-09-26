"""П. 1.3 через HTTP на реальных справочниках: журнал, «Не оповещено», статусы, ЧС/ЧП, дополнение, отработки."""

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
from tests.integration.test_card112 import card_body, resolve

FIRE_FLAT = "1050001"


@pytest.fixture(scope="module")
def app_client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Callable[[], TestClient]]:
    settings = make_settings(Path(tmp_path_factory.mktemp("db")) / "journal.db")
    create_schema(settings.database_url)
    seed_users(settings)
    asyncio.run(
        create_user(
            settings, login="petrov", full_name="Петров Пётр", role=Role.STUDENT, password=PASSWORD, operator_number="9"
        )
    )
    app = create_app(settings)
    with TestClient(app) as first:
        login(first, "admin")
        assert first.post("/api/v1/dictionaries/import").status_code == 200
        yield lambda: TestClient(app)


def as_user(make: Callable[[], TestClient], user: str) -> TestClient:
    c = make()
    login(c, user, arm="123")
    return c


def new_card(c: TestClient, *, extra_services: list[str] = (), **overrides: Any) -> dict[str, Any]:  # type: ignore[assignment]
    card = c.post("/api/v1/incidents/cards", json={"aon": "+7 (917) 980-54-13"}).json()
    services = [
        {"code": s["code"], "is_main": s["main"], "added_by": "auto"}
        for s in resolve(c, incident_type=[FIRE_FLAT], flag=["victims"], district="basmannyy")["services"]
    ]
    services += [{"code": code, "is_main": False, "added_by": "manual"} for code in extra_services]
    r = c.post(
        f"/api/v1/incidents/cards/{card['id']}/save", json={"data": card_body(**overrides), "services": services}
    )
    assert r.status_code == 200, r.text
    return card


def journal(c: TestClient, **params: Any) -> dict[str, Any]:
    r = c.get("/api/v1/incidents/journal", params=params)
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


def test_journal_rows_and_visibility(app_client: Callable[[], TestClient]) -> None:
    ivanov, petrov, teacher = (
        as_user(app_client, "student"),
        as_user(app_client, "petrov"),
        as_user(app_client, "teacher"),
    )
    mine = new_card(ivanov)
    draft = ivanov.post("/api/v1/incidents/cards", json={}).json()
    new_card(petrov, description="Петров: пожар в подвале, дым из окон подвала на первом этаже")

    rows = {r["number"]: r for r in journal(ivanov, page_size=100)["items"]}
    assert mine["number"] in rows and draft["number"] in rows
    assert all(r["author_name"] == "Обучающийся Тестовый" for r in rows.values())  # только свои
    row = rows[mine["number"]]
    assert row["display_status"] == "registered" and row["card_types"] == ["101"]
    assert row["address_line"] == "г. Москва, Новая Басманная улица, 6, (ЦАО, Басманный)"
    assert (row["has_victims"], row["victims_count"], row["arm_number"], row["operator_number"]) == (
        True,
        2,
        "123",
        "7",
    )
    assert rows[draft["number"]]["display_status"] == "draft"

    everyone = journal(teacher, page_size=100)
    assert {r["author_name"] for r in everyone["items"]} >= {"Обучающийся Тестовый", "Петров Пётр"}
    only_petrov = journal(teacher, q="ПЕТРОВ", page_size=100)["items"]
    assert only_petrov and {r["author_name"] for r in only_petrov} == {"Петров Пётр"}

    admin = as_user(app_client, "admin")
    assert admin.get("/api/v1/incidents/journal").status_code == 403


def test_search_filters_and_paging(app_client: Callable[[], TestClient]) -> None:
    c = as_user(app_client, "student")
    card = new_card(c, description="Уникальный запах гари у мусоропровода")
    assert [r["number"] for r in journal(c, q=str(card["number"]))["items"]] == [card["number"]]
    assert journal(c, q="МУСОРОПРОВОДА")["total"] >= 1
    assert journal(c, q="басманная")["total"] >= 1
    assert all(r["display_status"] == "draft" for r in journal(c, status="draft", page_size=100)["items"])
    page = journal(c, page_size=15)
    assert page["page"] == 1 and len(page["items"]) <= 15
    assert c.get("/api/v1/incidents/journal", params={"status": "unknown"}).json()["error"] == "bad_status_filter"


def test_not_notified_until_workout(app_client: Callable[[], TestClient]) -> None:
    c = as_user(app_client, "student")
    card = new_card(c, extra_services=["DEP_GKH"])  # «Деп. ЖКХ» — без интеграции
    assert journal(c, q=str(card["number"]))["items"][0]["display_status"] == "not_notified"
    assert any(r["number"] == card["number"] for r in journal(c, status="not_notified", page_size=100)["items"])

    r = c.post(
        f"/api/v1/incidents/cards/{card['id']}/workouts",
        json={
            "service_code": "DEP_GKH",
            "called_to": "дежурный",
            "phone": "+7 (495) 000-00-00",
            "receiver": "Сидоров",
            "message": "Передали адрес и суть",
        },
    )
    assert r.status_code == 201, r.text
    assert journal(c, q=str(card["number"]))["items"][0]["display_status"] == "registered"
    view = c.get(f"/api/v1/incidents/cards/{card['id']}").json()
    assert view["workouts"][0]["receiver"] == "Сидоров" and view["display_status"] == "registered"
    gkh = next(s for s in view["services"] if s["code"] == "DEP_GKH")
    assert gkh["integrated"] is False and gkh["history"][0]["status"] == "added"


def test_status_flow_by_roles(app_client: Callable[[], TestClient]) -> None:
    student, teacher = as_user(app_client, "student"), as_user(app_client, "teacher")
    card = new_card(student)
    base = f"/api/v1/incidents/cards/{card['id']}"
    assert student.post(f"{base}/checked", json={}).status_code == 403  # проверяет только преподаватель
    assert teacher.post(f"{base}/checked", json={}).json()["error"] == "bad_card_status"  # ещё не отработана
    assert student.post(f"{base}/worked", json={}).json() == {"status": "worked"}
    assert teacher.post(f"{base}/checked", json={}).json() == {"status": "checked"}
    row = journal(student, q=str(card["number"]))["items"][0]
    assert row["checked"] is True and row["display_status"] == "checked"
    assert teacher.post(f"{base}/returned", json={"comment": "уточните адрес"}).json() == {"status": "registered"}
    view = teacher.get(base).json()
    assert view["checked_by_name"] is None and view["status"] == "registered"


def test_flags_append_view_and_audit(app_client: Callable[[], TestClient]) -> None:
    student = as_user(app_client, "student")
    card = new_card(student)
    base = f"/api/v1/incidents/cards/{card['id']}"
    assert student.post(f"{base}/flags", json={"emergency": True, "incident": False}).json() == {"changed": ["ЧС"]}
    r = student.post(
        f"{base}/append",
        json={"fields": {"address.flat": "12"}, "description_add": "Дым на лестнице", "victims_count": 3},
    )
    assert r.json() == {"changed": ["квартира/офис", "описание", "пострадавшие"]}
    again = student.post(f"{base}/append", json={"fields": {"address.flat": "13"}})
    assert again.status_code == 422 and again.json()["error"] == "field_not_empty"
    assert student.post(f"{base}/viewed").status_code == 204

    view = student.get(base).json()
    assert view["is_emergency"] is True and view["data"]["address"]["flat"] == "12"
    assert view["data"]["description"].endswith("\nДым на лестнице") and view["data"]["victims"]["count"] == 3
    assert view["incident_types"][0]["final_type"] == "пожар: жилой дом"
    assert journal(student, q=str(card["number"]))["items"][0]["is_emergency"] is True

    admin = as_user(app_client, "admin")
    events = {
        e["event"]
        for e in admin.get("/api/v1/audit", params={"q": str(card["number"]), "page_size": 100}).json()["items"]
    }
    assert {"card.flags", "card.appended", "card.viewed", "card.saved"} <= events
