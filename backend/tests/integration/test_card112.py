"""П. 1.1 через HTTP на реальных справочниках: открыть карточку, автоподбор служб, сохранить, показать."""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from aiskra.main import create_app
from tests.integration.conftest import create_schema, login, make_settings, seed_users

FIRE_FLAT = "1050001"  # 101 → жилой дом → открытое пламя («пожар: жилой дом»)


@pytest.fixture(scope="module")
def app_client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Callable[[], TestClient]]:
    settings = make_settings(Path(tmp_path_factory.mktemp("db")) / "card.db")
    create_schema(settings.database_url)
    seed_users(settings)
    app = create_app(settings)
    with TestClient(app) as first:
        login(first, "admin")
        assert first.post("/api/v1/dictionaries/import").status_code == 200
        yield lambda: TestClient(app)


@pytest.fixture
def student(app_client: Callable[[], TestClient]) -> TestClient:
    c = app_client()
    login(c, "student", arm="123")
    return c


def card_body(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "phones": {"aon": "+7 (917) 980-54-13", "provided": "", "on_site": "", "foreign": False},
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
    data.update(overrides)
    return data


def resolve(c: TestClient, **params: Any) -> dict[str, Any]:
    r = c.get("/api/v1/dictionaries/services/resolve", params=params)
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


def test_resolve_services_for_fire_in_flat(student: TestClient) -> None:
    plain = resolve(student, incident_type=[FIRE_FLAT])
    shorts = [s["short"] for s in plain["services"]]
    assert plain["services"][0]["short"] == "Служба 101" and plain["services"][0]["main"] is True
    assert "Служба 103" not in shorts and plain["needs_address"] is True
    assert "MAYOR_OFFICE" in plain["monitoring"]

    full = resolve(student, incident_type=[FIRE_FLAT], flag=["victims"], district="basmannyy")
    codes = {s["code"] for s in full["services"]}
    assert {"S101", "S103", "PREF_CAO", "DDS_BASMANNYY"} <= codes and full["needs_address"] is False
    s103 = next(s for s in full["services"] if s["code"] == "S103")
    assert any("признак victims" in r for r in s103["reasons"])


def test_service_without_integration_is_marked(student: TestClient) -> None:
    """Стенд 2026: «Деп. ЖКХ» — серая плашка (служба без интеграции с системой 112)."""
    services = {s["code"]: s for s in student.get("/api/v1/dictionaries/services", params={"q": "жкх"}).json()}
    assert services["DEP_GKH"]["integrated"] is False
    resolved = resolve(student, incident_type=[FIRE_FLAT])["services"]
    assert all(s["integrated"] for s in resolved if s["code"] != "DEP_GKH")


def test_open_and_save_card(student: TestClient, app_client: Callable[[], TestClient]) -> None:
    opened = student.post("/api/v1/incidents/cards", json={"aon": "+7 (917) 980-54-13", "channel": "mts"})
    assert opened.status_code == 201, opened.text
    card = opened.json()
    assert card["number"] > 36_900_000

    services = [
        {"code": s["code"], "is_main": s["main"], "added_by": "auto"}
        for s in resolve(student, incident_type=[FIRE_FLAT], flag=["victims"], district="basmannyy")["services"]
    ]
    incomplete = student.post(
        f"/api/v1/incidents/cards/{card['id']}/save",
        json={"data": card_body(applicant={"name": "", "status": None}), "services": services},
    )
    assert incomplete.status_code == 422 and incomplete.json()["error"] == "card_incomplete"
    assert "Фамилия и имя заявителя" in incomplete.json()["message"]

    saved = student.post(f"/api/v1/incidents/cards/{card['id']}/save", json={"data": card_body(), "services": services})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["status"] == "registered" and body["number"] == card["number"] and body["processing_ms"] >= 0

    view = student.get(f"/api/v1/incidents/cards/{card['id']}").json()
    assert view["arm_number"] == "123" and view["operator_number"] == "7" and view["author_name"]
    assert view["data"]["address"]["house"] == "6" and view["data"]["services"] == [s["code"] for s in services]
    s101 = next(s for s in view["services"] if s["code"] == "S101")
    assert s101["is_main"] and s101["short"] == "Служба 101" and s101["status"] == "added"

    again = student.post(f"/api/v1/incidents/cards/{card['id']}/save", json={"data": card_body(), "services": services})
    assert again.json()["error"] == "card_already_saved"

    teacher = app_client()
    login(teacher, "teacher")
    assert teacher.get(f"/api/v1/incidents/cards/{card['id']}").status_code == 200

    admin = app_client()
    login(admin, "admin")
    events = admin.get("/api/v1/audit", params={"q": str(card["number"]), "by_card": True}).json()["items"]
    assert {e["event"] for e in events} == {"card.created", "card.saved"}
    assert all(e["card_number"] == card["number"] for e in events)


def test_empty_call_card(student: TestClient) -> None:
    card = student.post("/api/v1/incidents/cards", json={}).json()
    empty = {"data": {"flags": {"no_contact": True}}, "services": []}
    saved = student.post(f"/api/v1/incidents/cards/{card['id']}/save", json=empty).json()
    assert saved["status"] == "completed" and saved["services"] == []


def test_cards_are_private_and_student_only(student: TestClient, app_client: Callable[[], TestClient]) -> None:
    card = student.post("/api/v1/incidents/cards", json={}).json()
    admin = app_client()
    login(admin, "admin")
    assert admin.post("/api/v1/incidents/cards", json={}).status_code == 403  # нет права training.participate
    assert admin.get(f"/api/v1/incidents/cards/{card['id']}").status_code == 404
    bad = student.post(f"/api/v1/incidents/cards/{card['id']}/save", json={"data": {"unknown": 1}, "services": []})
    assert bad.status_code == 422
