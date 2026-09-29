"""П. 4.7 через HTTP: черновик отзыва (без модели — по правилам), сохранение с аудитом, отзыв в отчёте, CSV и в истории
обучающегося; права — только преподаватель занятия и только свой отзыв у обучающегося."""

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
from tests.integration.test_assessment import fill_from_reference

A = "/api/v1/assessment"


@pytest.fixture(scope="module")
def app_client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Callable[[], TestClient]]:
    settings = make_settings(Path(tmp_path_factory.mktemp("db")) / "feedback.db")
    create_schema(settings.database_url)
    seed_users(settings)
    for login_, name, role in (("petrov", "Петров Пётр", Role.STUDENT), ("teacher2", "Сидорова Анна", Role.TEACHER)):
        asyncio.run(
            create_user(settings, login=login_, full_name=name, role=role, password=PASSWORD, operator_number="9")
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


def new_session(teacher: TestClient, title: str, participants: list[dict[str, Any]]) -> str:
    body = {
        "title": title,
        "mode": "cards_112",
        "card_source": "generated",
        "groups": [1],
        "participants": participants,
    }
    sid = teacher.post("/api/v1/training/sessions", json=body).json()["id"]
    assert teacher.post(f"/api/v1/training/sessions/{sid}/start").status_code == 200
    return str(sid)


@pytest.fixture(scope="module")
def lesson(app_client: Callable[[], TestClient]) -> dict[str, Any]:
    """Занятие: оператор сохранил карточку с неверным домом; карточка оценена."""
    teacher, student = as_user(app_client, "teacher"), as_user(app_client, "student")
    for sid in teacher.post("/api/v1/training/scenarios/generate", json={"count": 1, "groups": [1]}).json()["ids"]:
        teacher.post(f"/api/v1/training/scenarios/{sid}/approve")
    people = {s["login"]: s["id"] for s in teacher.get("/api/v1/training/students").json()}
    session_id = new_session(
        teacher,
        "Отзыв: пожары",
        [{"student_id": people["student"], "role": "112"}, {"student_id": people["petrov"], "role": "112"}],
    )
    call = student.post("/api/v1/training/calls/incoming", json={"groups": [1]}).json()
    ref = teacher.get(f"/api/v1/training/scenarios/{call['scenario_id']}").json()["reference_card"]
    card = student.post(
        "/api/v1/incidents/cards",
        json={"aon": call["aon"], "scenario_id": call["scenario_id"], "session_id": session_id},
    ).json()
    data = fill_from_reference(ref, call["aon"])
    data["address"]["house"] = "999"
    services = [{"code": s["code"], "is_main": s["main"], "added_by": "auto"} for s in ref["services"]]
    r = student.post(f"/api/v1/incidents/cards/{card['id']}/save", json={"data": data, "services": services})
    assert r.status_code == 200, r.text
    assert teacher.post(f"{A}/sessions/{session_id}/evaluate").json()["assessed"] == 1
    return {"session_id": session_id, "people": people, "card_number": card["number"]}


def test_draft_by_rules_without_model(app_client: Callable[[], TestClient], lesson: dict[str, Any]) -> None:
    teacher = as_user(app_client, "teacher")
    url = f"{A}/sessions/{lesson['session_id']}/students/{lesson['people']['student']}/feedback/draft"
    r = teacher.post(url)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["source"] == "rules" and d["model"] is None and d["warnings"] == [] and d["previous"] is None
    assert d["text"].startswith("Занятие «Отзыв: пожары»: 1 карточка, средний балл")
    assert "Что подтянуть:\n— Адрес" in d["text"] and f"карточка № {lesson['card_number']}" in d["text"]
    assert "Следующий шаг:" in d["text"]
    assert d["focus"][0]["key"] == "address"

    # у Петрова карточек нет — черновик честно об этом говорит
    empty = teacher.post(f"{A}/sessions/{lesson['session_id']}/students/{lesson['people']['petrov']}/feedback/draft")
    assert empty.json()["warnings"] == ["В этом занятии у обучающегося нет сохранённых карточек."]


def test_feedback_access(app_client: Callable[[], TestClient], lesson: dict[str, Any]) -> None:
    base = f"{A}/sessions/{lesson['session_id']}/students/{lesson['people']['student']}/feedback"
    body = {"text": "Хорошая работа, подтяните адрес."}
    student, other = as_user(app_client, "student"), as_user(app_client, "teacher2")
    assert student.post(f"{base}/draft").status_code == 403
    assert student.put(base, json=body).status_code == 403
    assert other.post(f"{base}/draft").status_code == 404  # чужое занятие
    assert other.put(base, json=body).status_code == 404
    stranger = f"{A}/sessions/{lesson['session_id']}/students/00000000-0000-0000-0000-000000000001/feedback"
    teacher = as_user(app_client, "teacher")
    assert teacher.put(stranger, json=body).json()["error"] == "participant_not_found"
    assert teacher.put(base, json={"text": "коротко"}).status_code == 422
    assert TestClient(teacher.app).get(f"{A}/my/feedback").status_code == 401


def test_save_edit_and_student_history(app_client: Callable[[], TestClient], lesson: dict[str, Any]) -> None:
    teacher, student, petrov = (as_user(app_client, u) for u in ("teacher", "student", "petrov"))
    sid, uid = lesson["session_id"], lesson["people"]["student"]
    base = f"{A}/sessions/{sid}/students/{uid}/feedback"
    draft = teacher.post(f"{base}/draft").json()
    edited = draft["text"] + "\n\nОтдельно: хорошо держали разговор."
    r = teacher.put(base, json={"text": edited, "draft_text": draft["text"], "draft_source": draft["source"]})
    assert r.status_code == 200, r.text
    assert r.json()["text"] == edited and r.json()["updated_at"]

    report = teacher.get(f"{A}/sessions/{sid}/report").json()
    rows = {s["full_name"]: s for s in report["students"]}
    assert rows["Обучающийся Тестовый"]["feedback"]["text"] == edited
    assert rows["Петров Пётр"]["feedback"] is None
    csv = teacher.get(f"{A}/sessions/{sid}/report.csv").content.decode("utf-8")
    assert "Отзыв преподавателя" in csv and "хорошо держали разговор" in csv

    # правка заменяет текст, отзыв остаётся один
    final = "Итог: адрес — из справочника. Следующий шаг: сверяйте дом."
    assert teacher.put(base, json={"text": final}).status_code == 200
    mine = student.get(f"{A}/my/feedback").json()
    assert [(x["session_id"], x["text"], x["session_title"]) for x in mine] == [(sid, final, "Отзыв: пожары")]
    assert student.get(f"{A}/sessions/{sid}/mine").json()["report"]["students"][0]["feedback"]["text"] == final
    assert petrov.get(f"{A}/my/feedback").json() == []  # чужой отзыв не виден
    assert petrov.get(f"{A}/sessions/{sid}/mine").json()["report"]["students"][0]["feedback"] is None

    admin = as_user(app_client, "admin")
    events = [
        e
        for e in admin.get("/api/v1/audit", params={"page_size": 100}).json()["items"]
        if e["event"] == "assessment.feedback_saved"
    ]
    assert (
        len(events) == 2
        and events[0]["actor_login"] == "teacher"
        and events[0]["event_title"] == "Отзыв преподавателя по занятию"
    )
    assert events[0]["description"].startswith("Обучающийся Тестовый · «Отзыв: пожары»: Итог: адрес")


def test_next_draft_remembers_previous_feedback(app_client: Callable[[], TestClient], lesson: dict[str, Any]) -> None:
    teacher = as_user(app_client, "teacher")
    uid = lesson["people"]["student"]
    base = f"{A}/sessions/{lesson['session_id']}/students/{uid}/feedback"
    teacher.put(base, json={"text": "Подтяните адрес: дом — из справочника."})
    second = new_session(teacher, "Отзыв: второе занятие", [{"student_id": uid, "role": "112"}])
    d = teacher.post(f"{A}/sessions/{second}/students/{uid}/feedback/draft").json()
    assert d["previous"]["session_title"] == "Отзыв: пожары"
    assert d["previous"]["text"] == "Подтяните адрес: дом — из справочника."
