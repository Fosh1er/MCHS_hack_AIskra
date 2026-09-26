"""Адресный справочник и карта (п. 1.2): импорт data/dictionaries, подсказки, адрес по точке, дома, границы."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aiskra.main import create_app
from tests.integration.conftest import create_schema, login, make_settings, seed_users


@pytest.fixture(scope="module")
def app(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    """Импорт 120+ тыс. домов занимает секунды — один раз на модуль."""
    settings = make_settings(Path(tmp_path_factory.mktemp("db")) / "addr.db")
    create_schema(settings.database_url)
    seed_users(settings)
    with TestClient(create_app(settings)) as c:
        login(c, "admin")
        assert c.post("/api/v1/dictionaries/import").status_code == 200
        r = c.post("/api/v1/dictionaries/addresses/import")
        assert r.status_code == 200, r.text
        c.report = r.json()  # type: ignore[attr-defined]
        yield c


def test_import_counts(app: TestClient) -> None:
    counts = app.report["counts"]  # type: ignore[attr-defined]
    assert counts["houses"] > 100_000 and counts["streets"] > 4_000 and counts["shapes"] >= 130
    audit = app.get("/api/v1/audit", params={"event": "dictionaries.addresses_imported"}).json()
    assert audit["total"] == 1


def test_import_requires_permission(app: TestClient) -> None:
    teacher = TestClient(app.app)
    login(teacher, "teacher")
    assert teacher.post("/api/v1/dictionaries/addresses/import").status_code == 403


def test_suggest_houses_and_streets(app: TestClient) -> None:
    student = TestClient(app.app)
    login(student, "student")
    houses = student.get("/api/v1/dictionaries/addresses/suggest", params={"q": "Щелковское ш 44"}).json()
    assert houses[0]["label"].startswith("Щёлковское шоссе, 44")
    assert houses[0]["district"] == "severnoe_izmaylovo" and houses[0]["okrug"] == "VAO"
    assert houses[0]["lat"] and houses[0]["source"] == "справочник"
    same_name = student.get("/api/v1/dictionaries/addresses/suggest", params={"q": "3-й Дорожный проезд, 1"}).json()
    assert {s["district"] for s in same_name if s["house"] == "1"} >= {"chertanovo_yuzhnoe"}
    streets = student.get("/api/v1/dictionaries/addresses/suggest", params={"q": "тверская"}).json()
    assert any(s["label"] == "Тверская улица" and s["house"] == "" for s in streets)
    assert student.get("/api/v1/dictionaries/addresses/suggest", params={"q": "13"}).json() == []


def test_reverse_geocode_and_houses(app: TestClient) -> None:
    r = app.get("/api/v1/dictionaries/addresses/reverse", params={"lat": 55.7652, "lon": 37.6667}).json()
    assert r["district"] == "basmannyy" and r["okrug"] == "CAO"
    assert r["address"] and r["distance_m"] <= 120
    far = app.get("/api/v1/dictionaries/addresses/reverse", params={"lat": 50.0, "lon": 30.0}).json()
    assert far["district"] is None and far["address"] is None
    assert app.get("/api/v1/dictionaries/addresses/reverse", params={"lat": 95, "lon": 0}).status_code == 422
    box = {"min_lat": 55.764, "min_lon": 37.66, "max_lat": 55.767, "max_lon": 37.67}
    assert len(app.get("/api/v1/dictionaries/addresses/houses", params=box).json()) > 5
    wide = {"min_lat": 55.5, "min_lon": 37.3, "max_lat": 55.9, "max_lon": 37.9}
    assert app.get("/api/v1/dictionaries/addresses/houses", params=wide).json() == []


def test_district_shapes(app: TestClient) -> None:
    geo = app.get("/api/v1/dictionaries/territory/shapes").json()
    assert geo["type"] == "FeatureCollection" and "OpenStreetMap" in geo["attribution"]
    codes = {f["properties"]["code"] for f in geo["features"]}
    assert {"basmannyy", "arbat", "troitsk"} <= codes
