"""Обучение интерфейсу (п. 5.3): прогресс хранится за учётной записью и виден только ей."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.integration.conftest import login

URL = "/api/v1/auth/onboarding"


def _as(app_client: Callable[[], TestClient], user: str) -> TestClient:
    c = app_client()
    login(c, user)
    return c


def test_requires_session(client: TestClient) -> None:
    assert client.get(URL).status_code == 401
    assert client.post(URL, json={"action": "dismiss"}).status_code == 401


def test_only_trainee_gets_tours_automatically(app_client: Callable[[], TestClient]) -> None:
    student = _as(app_client, "student").get(URL).json()
    assert student == {"enabled": True, "dismissed": False, "seen": []}
    assert _as(app_client, "teacher").get(URL).json()["enabled"] is False
    assert _as(app_client, "admin").get(URL).json()["enabled"] is False


def test_progress_is_saved_per_user(app_client: Callable[[], TestClient]) -> None:
    student = _as(app_client, "student")
    r = student.post(URL, json={"action": "seen", "tour": "journal-112"})
    assert r.status_code == 200 and r.json()["seen"] == ["journal-112"]
    student.post(URL, json={"action": "seen", "tour": "card-112"})

    # другой компьютер класса — тот же прогресс
    again = _as(app_client, "student").get(URL).json()
    assert again["seen"] == ["journal-112", "card-112"]
    # чужой прогресс не затронут
    assert _as(app_client, "teacher").get(URL).json()["seen"] == []


def test_dismiss_hides_everything(app_client: Callable[[], TestClient]) -> None:
    student = _as(app_client, "student")
    assert student.post(URL, json={"action": "dismiss"}).json()["dismissed"] is True
    assert _as(app_client, "student").get(URL).json()["dismissed"] is True


def test_reset_starts_over(app_client: Callable[[], TestClient]) -> None:
    student = _as(app_client, "student")
    student.post(URL, json={"action": "seen", "tour": "welcome"})
    student.post(URL, json={"action": "dismiss"})
    assert student.post(URL, json={"action": "reset"}).json() == {"enabled": True, "dismissed": False, "seen": []}


def test_bad_tour_rejected(app_client: Callable[[], TestClient]) -> None:
    student = _as(app_client, "student")
    r = student.post(URL, json={"action": "seen", "tour": "Не экран"})
    assert r.status_code == 422 and r.json()["error"] == "bad_tour"
    assert student.post(URL, json={"action": "seen"}).json()["error"] == "bad_tour"
    assert student.post(URL, json={"action": "fly"}).status_code == 422
