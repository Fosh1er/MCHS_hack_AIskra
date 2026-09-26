"""П. 5.1 через HTTP: мои занятия, мои результаты по занятию с рекомендациями, чужое занятие недоступно."""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from tests.integration.test_assessment import fill_from_reference
from tests.integration.test_journal import app_client as journal_app_client  # noqa: F401
from tests.integration.test_journal import as_user


@pytest.fixture(scope="module")
def app_client(journal_app_client: Callable[[], TestClient]) -> Iterator[Callable[[], TestClient]]:  # noqa: F811
    yield journal_app_client


def test_my_sessions_and_results(app_client: Callable[[], TestClient]) -> None:
    teacher, student, petrov = (as_user(app_client, u) for u in ("teacher", "student", "petrov"))
    for sid in teacher.post("/api/v1/training/scenarios/generate", json={"count": 1, "groups": [1]}).json()["ids"]:
        teacher.post(f"/api/v1/training/scenarios/{sid}/approve")
    people = {s["login"]: s["id"] for s in teacher.get("/api/v1/training/students").json()}
    body = {
        "title": "Кабинет: пожары",
        "mode": "cards_112",
        "groups": [1],
        "participants": [{"student_id": people["student"], "role": "112"}],
    }
    session_id = teacher.post("/api/v1/training/sessions", json=body).json()["id"]

    mine = student.get("/api/v1/training/sessions/mine").json()
    row = next(r for r in mine if r["session_id"] == session_id)
    assert row["status"] == "planned" and row["role"] == "112"
    assert all(r["session_id"] != session_id for r in petrov.get("/api/v1/training/sessions/mine").json())
    teacher.post(f"/api/v1/training/sessions/{session_id}/start")
    assert student.get("/api/v1/training/sessions/mine").json()[0]["status"] == "running"  # идущее — первым

    call = student.post("/api/v1/training/calls/incoming", json={"groups": [1]}).json()
    ref = teacher.get(f"/api/v1/training/scenarios/{call['scenario_id']}").json()["reference_card"]
    card = student.post(
        "/api/v1/incidents/cards",
        json={"aon": call["aon"], "scenario_id": call["scenario_id"], "session_id": session_id},
    ).json()
    data = fill_from_reference(ref, call["aon"])
    data["victims"] = {"has": not ref["victims"]["has"], "count": 0 if ref["victims"]["has"] else 2}  # ошибка
    services = [{"code": s["code"], "is_main": s["main"], "added_by": "auto"} for s in ref["services"]]
    student.post(f"/api/v1/incidents/cards/{card['id']}/save", json={"data": data, "services": services})
    teacher.post(f"/api/v1/training/sessions/{session_id}/finish")
    teacher.post(f"/api/v1/assessment/sessions/{session_id}/evaluate")

    mine = student.get(f"/api/v1/assessment/sessions/{session_id}/mine").json()
    assert [s["full_name"] for s in mine["report"]["students"]] == ["Обучающийся Тестовый"]
    assert mine["report"]["students"][0]["cards"][0]["card_number"] == card["number"]
    recs = {r["key"]: r["text"] for r in mine["recommendations"]}
    assert "victims" in recs and "пострадавшие" in recs["victims"].lower()
    assert petrov.get(f"/api/v1/assessment/sessions/{session_id}/mine").status_code == 404
    progress = student.get("/api/v1/assessment/my/progress").json()
    assert any(r["key"] == "victims" for r in progress["recommendations"])
