"""П. 4.1–4.3 через HTTP: банк сценариев (фильтры, правка, прогон), занятие (создание, старт, поток карточек в ДДС,
мониторинг), отчёт (оценка всех карточек, CSV, экспертная правка) и прогресс обучающегося."""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from tests.integration.test_assessment import fill_from_reference
from tests.integration.test_journal import app_client as journal_app_client  # noqa: F401
from tests.integration.test_journal import as_user


@pytest.fixture(scope="module")
def app_client(journal_app_client: Callable[[], TestClient]) -> Iterator[Callable[[], TestClient]]:  # noqa: F811
    yield journal_app_client


def test_scenario_bank_filters_edit_preview(app_client: Callable[[], TestClient]) -> None:
    teacher = as_user(app_client, "teacher")
    ids = teacher.post("/api/v1/training/scenarios/generate", json={"count": 2, "groups": [1], "difficulty": 4}).json()[
        "ids"
    ]
    page = teacher.get("/api/v1/training/scenarios", params={"difficulty": 4}).json()
    assert page["total"] >= 2 and all(s["difficulty"] == 4 for s in page["items"])
    assert teacher.post(f"/api/v1/training/scenarios/{ids[0]}/approve").json()["status"] == "approved"

    r = teacher.patch(f"/api/v1/training/scenarios/{ids[0]}", json={"title": "Пожар в квартире, дым из окна"})
    assert r.status_code == 200 and r.json()["status"] == "draft"  # правка возвращает на проверку
    s = teacher.get(f"/api/v1/training/scenarios/{ids[0]}").json()
    assert s["title"] == "Пожар в квартире, дым из окна"
    r = teacher.patch(f"/api/v1/training/scenarios/{ids[0]}", json={"comment": "Сделай заявителя растерянным"})
    assert r.status_code == 422 and r.json()["error"] == "ai_unavailable"  # офлайн-режим — честный отказ

    preview = teacher.get(f"/api/v1/training/scenarios/{ids[1]}/preview").json()
    assert len(preview) >= 4 and all(p["question"] and p["answer"] and p["reference"] for p in preview)
    student = as_user(app_client, "student")
    assert student.patch(f"/api/v1/training/scenarios/{ids[0]}", json={"title": "xxx"}).status_code == 403


def test_session_lifecycle_monitor_report(app_client: Callable[[], TestClient]) -> None:
    teacher, student, petrov = (as_user(app_client, u) for u in ("teacher", "student", "petrov"))
    ids = teacher.post("/api/v1/training/scenarios/generate", json={"count": 2, "groups": [1]}).json()["ids"]
    for sid in ids:
        teacher.post(f"/api/v1/training/scenarios/{sid}/approve")
    scenario = teacher.get(f"/api/v1/training/scenarios/{ids[0]}").json()
    dds_code = scenario["reference_card"]["services"][0]["code"]

    groups = teacher.get("/api/v1/dictionaries/incident-groups").json()
    assert groups[0]["id"] == 1 and groups[0]["title"]
    people = {s["login"]: s["id"] for s in teacher.get("/api/v1/training/students").json()}
    assert {"student", "petrov"} <= people.keys() and "teacher" not in people
    body = {
        "title": "Занятие: пожары",
        "mode": "mixed",
        "card_source": "generated",
        "groups": [1],
        "participants": [
            {"student_id": people["student"], "role": "112"},
            {"student_id": people["petrov"], "role": "dds", "dds_service_code": dds_code},
        ],
        "settings": {"norm_112": 80, "feed_interval_s": 60, "max_waiting": 2},
    }
    bad = {**body, "participants": [{"student_id": people["petrov"], "role": "dds"}]}
    assert teacher.post("/api/v1/training/sessions", json=bad).status_code == 422
    assert student.post("/api/v1/training/sessions", json=body).status_code == 403
    r = teacher.post("/api/v1/training/sessions", json=body)
    assert r.status_code == 201, r.text
    session_id = r.json()["id"]

    assert student.get("/api/v1/training/sessions/my").json() is None  # ещё не начато
    assert petrov.post("/api/v1/training/sessions/feed").json()["card_id"] is None
    assert teacher.post(f"/api/v1/training/sessions/{session_id}/start").json()["status"] == "running"
    assert teacher.post(f"/api/v1/training/sessions/{session_id}/start").status_code == 422
    my = student.get("/api/v1/training/sessions/my").json()
    assert my["session_id"] == session_id and my["role"] == "112" and my["groups"] == [1]
    assert petrov.get("/api/v1/training/sessions/my").json()["dds_service_code"] == dds_code

    fed = petrov.post("/api/v1/training/sessions/feed").json()
    assert fed["card_id"] and fed["waiting"] == 1
    assert petrov.post("/api/v1/training/sessions/feed").json()["reason"] == "рано"  # темп занятия
    base = f"/api/v1/incidents/dds/{dds_code}/cards/{fed['card_id']}"
    assert petrov.post(f"{base}/received").status_code == 200
    r = petrov.post(f"{base}/status", json={"status": "accepted", "order_no": "12", "comment": "Бригада выехала"})
    assert r.status_code == 200, r.text

    call = student.post("/api/v1/training/calls/incoming", json={"groups": [1]}).json()
    ref = teacher.get(f"/api/v1/training/scenarios/{call['scenario_id']}").json()["reference_card"]
    card = student.post(
        "/api/v1/incidents/cards",
        json={"aon": call["aon"], "scenario_id": call["scenario_id"], "session_id": session_id},
    ).json()
    services = [{"code": s["code"], "is_main": s["main"], "added_by": "auto"} for s in ref["services"]]
    r = student.post(
        f"/api/v1/incidents/cards/{card['id']}/save",
        json={"data": fill_from_reference(ref, call["aon"]), "services": services},
    )
    assert r.status_code == 200, r.text

    mon = teacher.get(f"/api/v1/training/sessions/{session_id}/monitor").json()
    rows = {row["participant"]["role"]: row["progress"] for row in mon["rows"]}
    assert {p["full_name"] for p in mon["session"]["participants"]} == {"Обучающийся Тестовый", "Петров Пётр"}
    assert mon["session"]["status"] == "running" and rows["112"]["cards_done"] == 1
    assert rows["dds"]["current_card"] is not None and rows["dds"]["waiting"] == 1
    assert student.get(f"/api/v1/training/sessions/{session_id}/monitor").status_code == 403

    summary = teacher.post(f"/api/v1/assessment/sessions/{session_id}/evaluate").json()
    assert summary["assessed"] >= 2
    report = teacher.get(f"/api/v1/assessment/sessions/{session_id}/report").json()
    by_role = {s["role"]: s for s in report["students"]}
    assert by_role["112"]["full_name"] == "Обучающийся Тестовый" and by_role["dds"]["full_name"] == "Петров Пётр"
    op = by_role["112"]["cards"][0]
    assert op["card_number"] == card["number"] and op["score"] >= 90 and op["norm_s"] == 80
    assert by_role["dds"]["cards"][0]["score"] is not None
    assert report["heatmap"]["criteria"] and len(report["heatmap"]["rows"]) == 2
    assert sum(b["count"] for b in report["time_buckets"]) == 1

    csv = teacher.get(f"/api/v1/assessment/sessions/{session_id}/report.csv")
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    assert "ФИО;Роль" in csv.text and str(card["number"]) in csv.text

    r = teacher.post(f"/api/v1/assessment/{op['assessment_id']}/override", json={"score": 55, "comment": "Н"})
    assert r.status_code == 422  # причина правки обязательна
    r = teacher.post(
        f"/api/v1/assessment/{op['assessment_id']}/override",
        json={"score": 55, "comment": "Описание не отражает обстановку"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["grader"] == "expert" and r.json()["score"] == 55 and not r.json()["passed"]
    assert r.json()["details"]["expert"]["auto_score"] == op["score"]
    assert (
        student.post(
            f"/api/v1/assessment/{op['assessment_id']}/override", json={"score": 100, "comment": "Хочу сто"}
        ).status_code
        == 403
    )
    again = teacher.get(f"/api/v1/assessment/sessions/{session_id}/report").json()
    assert next(s for s in again["students"] if s["role"] == "112")["cards"][0]["expert"] is True

    # повторная автопроверка не затирает экспертную оценку
    redo = student.post(f"/api/v1/assessment/cards/{card['id']}/evaluate", json={"role": "112"}).json()
    assert redo["score"] == 55 and redo["grader"] == "expert" and redo["details"]["expert"]["auto_score"] == op["score"]
    csv2 = teacher.get(f"/api/v1/assessment/sessions/{session_id}/report.csv").text
    header = csv2.splitlines()[2].split(";")
    row = next(line.split(";") for line in csv2.splitlines() if str(card["number"]) in line)
    assert len(header) == len(row) and row[header.index("Комментарий эксперта")] == "Описание не отражает обстановку"
    progress = student.get("/api/v1/assessment/my/progress").json()
    assert progress["expert_comments"][0]["comment"] == "Описание не отражает обстановку"
    assert progress["points"] and progress["points"][-1]["v"] == 55

    assert teacher.post(f"/api/v1/training/sessions/{session_id}/finish").json()["status"] == "finished"
    assert student.get("/api/v1/training/sessions/my").json() is None
    listed = teacher.get("/api/v1/training/sessions").json()
    assert any(s["id"] == session_id and s["status"] == "finished" for s in listed["items"])
    admin = as_user(app_client, "admin")
    events = {e["event"] for e in admin.get("/api/v1/audit", params={"page_size": 100}).json()["items"]}
    assert {"sessions.created", "sessions.started", "sessions.finished", "assessment.overridden"} <= events
