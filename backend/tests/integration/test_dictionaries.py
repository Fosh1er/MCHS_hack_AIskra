"""Импорт реальных данных заказчика (data/) и API справочников."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aiskra.main import create_app
from tests.integration.conftest import create_schema, login, make_settings, seed_users


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    """Импорт реального классификатора занимает секунды — делаем его один раз на модуль."""
    settings = make_settings(Path(tmp_path_factory.mktemp("db")) / "dict.db")
    create_schema(settings.database_url)
    seed_users(settings)
    with TestClient(create_app(settings)) as c:
        login(c, "admin")
        r = c.post("/api/v1/dictionaries/import")
        assert r.status_code == 200, r.text
        c.first_report = r.json()  # type: ignore[attr-defined]
        yield c


def test_import_counts_match_customer_data(client: TestClient) -> None:
    counts = client.first_report["counts"]  # type: ignore[attr-defined]
    assert counts["groups"] == 24
    assert counts["incident_types"] == 1281
    assert counts["incident_types_visible_to_112"] == 1281 - 144
    assert counts["service_columns"] == 76
    assert counts["routing_cells"] > 20_000
    assert counts["card_types"] == 51
    assert counts["okrugs"] == 13 and counts["districts"] == 146
    assert counts["brigades"] >= 2 * counts["services"]  # п. 5.5: у каждой службы — не меньше двух бригад
    warnings = " ".join(client.first_report["warnings"])  # type: ignore[attr-defined]
    assert "групп [24]" in warnings and "Карточки-112" in warnings


def test_import_is_idempotent(client: TestClient) -> None:
    second = client.post("/api/v1/dictionaries/import").json()
    assert second["counts"] == client.first_report["counts"]  # type: ignore[attr-defined]
    assert second["deactivated"] == {"incident_types": 0, "services": 0, "brigades": 0, "districts": 0}


def test_card_type_search_with_synonyms(client: TestClient) -> None:
    fire = client.get("/api/v1/dictionaries/card-types", params={"q": "пожар"}).json()
    assert fire[0]["code"] == "101"
    gas = [c["code"] for c in client.get("/api/v1/dictionaries/card-types", params={"q": "запах газа"}).json()]
    assert "104" in gas
    quick = client.get("/api/v1/dictionaries/card-types", params={"quick": True}).json()
    assert {"dtp", "104", "person_danger"} <= {c["code"] for c in quick}


def test_questionnaire_tree_for_fire(client: TestClient) -> None:
    tree = client.get("/api/v1/dictionaries/card-types/101/questionnaire").json()
    labels = {n["label"] for n in tree["roots"]}
    assert {"жилой дом", "на улице", "транспорт"} <= labels
    assert "Не отображается оператору 112" not in labels
    assert tree["types_count"] == 271 - 144
    service_only = client.get("/api/v1/dictionaries/card-types/wrong_number/questionnaire").json()
    assert service_only["roots"] == [] and service_only["types_count"] == 0


def test_incident_type_with_routing(client: TestClient) -> None:
    body = client.get("/api/v1/dictionaries/incident-types/1010101").json()
    assert body["type"]["sign1"] == "на улице" and body["type"]["group_title"] == "Пожары и задымления"
    cells = {c["col"]: c for c in body["routing"]}
    assert cells[15]["service"] == "S101" and cells[15]["service_type"] == "пожар: мусор"
    assert cells[15]["service_short"] == "Служба 101"
    assert cells[27]["delivery"] == "no_response"  # СМП: пострадавший не на месте
    assert client.get("/api/v1/dictionaries/incident-types/99999999").status_code == 404


def test_incident_type_search(client: TestClient) -> None:
    page = client.get("/api/v1/dictionaries/incident-types", params={"q": "лифт", "limit": 5}).json()
    assert page["total"] > 0 and len(page["items"]) <= 5
    assert all(
        "лифт" in (i["sign1"] or "").lower() + (i["sign2"] or "").lower() + (i["final_type"] or "").lower()
        for i in page["items"]
    )


def test_services_and_territory(client: TestClient) -> None:
    dds = client.get("/api/v1/dictionaries/services", params={"q": "вороновское"}).json()
    assert dds and dds[0]["kind"] == "district_dds" and dds[0]["phone_synthetic"] is True
    tao = client.get("/api/v1/dictionaries/territory", params={"okrug": "TAO"}).json()
    assert len(tao["districts"]) == 10 and len(tao["okrugs"]) == 13
    sav = client.get("/api/v1/dictionaries/territory", params={"q": "савелки"}).json()["districts"]
    assert sav and sav[0]["name"] == "Савёлки"


def test_enums(client: TestClient) -> None:
    statuses = client.get("/api/v1/dictionaries/enums/applicant_status").json()
    assert [s["name"] for s in statuses][:2] == ["очевидец", "пострадавший"] and len(statuses) == 6
    channels = client.get("/api/v1/dictionaries/enums/channel").json()
    assert any(c["name"] == "МГТС-112" for c in channels)
    r = client.get("/api/v1/dictionaries/enums/unknown")
    assert r.status_code == 404 and "applicant_status" in r.json()["message"]


def test_import_is_audited_and_admin_only(client: TestClient) -> None:
    items = client.get("/api/v1/audit", params={"event": "dictionaries.imported"}).json()["items"]
    assert items and items[-1]["actor_login"] == "admin" and "1281 типов" in items[-1]["description"]
    student = TestClient(client.app)
    login(student, "student")
    assert student.get("/api/v1/dictionaries/card-types", params={"q": "пожар"}).status_code == 200
    assert student.post("/api/v1/dictionaries/import").status_code == 403
