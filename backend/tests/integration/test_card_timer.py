"""П. 5.3: пауза таймера карточки через API — только автору, всего до 10 минут, каждая — в журнал аудита."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import login


@pytest.fixture
def student(app_client: Callable[[], TestClient]) -> TestClient:
    c = app_client()
    login(c, "student")
    return c


def test_pause_and_resume(student: TestClient, app_client: Callable[[], TestClient]) -> None:
    card = student.post("/api/v1/incidents/cards", json={}).json()
    url = f"/api/v1/incidents/cards/{card['id']}/timer"

    assert student.post(url, json={"paused": True}).status_code == 200
    view = student.get(f"/api/v1/incidents/cards/{card['id']}").json()
    assert view["timer_paused"] is True

    resumed = student.post(url, json={"paused": False})
    assert resumed.status_code == 200 and resumed.json()["paused_ms"] >= 0
    view = student.get(f"/api/v1/incidents/cards/{card['id']}").json()
    assert view["timer_paused"] is False and view["paused_ms"] == resumed.json()["paused_ms"]

    assert student.post(url, json={"paused": True}).status_code == 200  # вторая пауза — в пределах 10 минут
    student.post(url, json={"paused": False})

    admin = app_client()
    login(admin, "admin")
    audit = admin.get("/api/v1/audit", params={"event": "card.timer_paused"}).json()
    assert audit["total"] == 2 and audit["items"][0]["card_number"] == card["number"]


def test_only_author_can_pause(student: TestClient, app_client: Callable[[], TestClient]) -> None:
    card = student.post("/api/v1/incidents/cards", json={}).json()
    teacher = app_client()
    login(teacher, "teacher")
    r = teacher.post(f"/api/v1/incidents/cards/{card['id']}/timer", json={"paused": True})
    assert r.status_code == 403  # нет права training.participate
