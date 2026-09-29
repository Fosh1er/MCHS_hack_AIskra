"""П. 3.6 через HTTP: занятие с психологическим модификатором → звонок с профилем → разметка реплик → блок оценки
«Работа с заявителем»; закрепление профиля за сценарием; пауза; права."""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from tests.integration.test_assessment import fill_from_reference
from tests.integration.test_journal import app_client as journal_app_client  # noqa: F401
from tests.integration.test_journal import as_user


@pytest.fixture(scope="module")
def app_client(journal_app_client: Callable[[], TestClient]) -> Iterator[Callable[[], TestClient]]:  # noqa: F811
    yield journal_app_client


def _session(teacher: TestClient, student_id: str, psy: dict[str, object]) -> str:
    body = {
        "title": "Занятие: сложный заявитель",
        "mode": "cards_112",
        "card_source": "generated",
        "groups": [1],
        "participants": [{"student_id": student_id, "role": "112"}],
        "settings": {"psy": psy},
    }
    r = teacher.post("/api/v1/training/sessions", json=body)
    assert r.status_code == 201, r.text
    sid: str = r.json()["id"]
    assert teacher.post(f"/api/v1/training/sessions/{sid}/start").json()["status"] == "running"
    return sid


def test_psy_catalog_and_scenario_profile(app_client: Callable[[], TestClient]) -> None:
    teacher, student = as_user(app_client, "teacher"), as_user(app_client, "student")
    profiles = teacher.get("/api/v1/training/psy/profiles").json()
    ids = {p["id"] for p in profiles}
    assert {"panic", "crying", "aggression", "suicidal"} <= ids
    assert all(p["sources"] for p in profiles)
    assert student.get("/api/v1/training/psy/profiles").status_code == 403

    sid = teacher.post("/api/v1/training/scenarios/generate", json={"count": 1, "groups": [1]}).json()["ids"][0]
    assert (
        teacher.post(f"/api/v1/training/scenarios/{sid}/psy", json={"profile": "crying"}).json()["status"] == "crying"
    )
    assert teacher.get(f"/api/v1/training/scenarios/{sid}").json()["psy_profile"] == "crying"
    bad = teacher.post(f"/api/v1/training/scenarios/{sid}/psy", json={"profile": "ghost"})
    assert bad.status_code == 422 and bad.json()["error"] == "unknown_psy_profile"
    assert student.post(f"/api/v1/training/scenarios/{sid}/psy", json={"profile": "panic"}).status_code == 403
    assert teacher.post(f"/api/v1/training/scenarios/{sid}/psy", json={"profile": None}).json()["status"] == "none"


def test_session_with_modifier_call_and_block(app_client: Callable[[], TestClient]) -> None:
    teacher, student = as_user(app_client, "teacher"), as_user(app_client, "student")
    for sid in teacher.post("/api/v1/training/scenarios/generate", json={"count": 2, "groups": [1]}).json()["ids"]:
        teacher.post(f"/api/v1/training/scenarios/{sid}/approve")
    people = {s["login"]: s["id"] for s in teacher.get("/api/v1/training/students").json()}
    unknown = teacher.post(
        "/api/v1/training/sessions",
        json={
            "title": "Ошибка",
            "mode": "cards_112",
            "participants": [{"student_id": people["student"], "role": "112"}],
            "settings": {"psy": {"enabled": True, "profiles": ["ghost"]}},
        },
    )
    assert unknown.status_code == 422 and unknown.json()["error"] == "bad_psy_setting"
    session_id = _session(teacher, people["student"], {"enabled": True, "share": 1, "profiles": ["panic"]})

    call = student.post("/api/v1/training/calls/incoming", json={"groups": [1]}).json()
    assert call["warning"] is None  # паника — не кризисный профиль
    ref = teacher.get(f"/api/v1/training/scenarios/{call['scenario_id']}").json()["reference_card"]
    card = student.post("/api/v1/incidents/cards", json={"aon": call["aon"], "scenario_id": call["scenario_id"]}).json()
    opening = student.post(f"/api/v1/training/calls/{call['call_id']}/answer", json={"card_id": card["id"]}).json()
    assert opening["voice"]["profile"] == "panic" and opening["voice"]["level"] == 4
    say = f"/api/v1/training/calls/{call['call_id']}/replicas"
    r = student.post(say, json={"text": "Успокойтесь! Назовите адрес."}).json()
    assert r["voice"]["level"] == 5 and "[" not in r["text"]  # ремарки — отдельно от озвучиваемого текста
    for text in (
        "Я на линии, помощь уже направляю. Мне нужен адрес, чтобы направить помощь. Назовите адрес.",
        "Мне нужен адрес, чтобы направить помощь. Назовите адрес.",
        "Дышите со мной: медленный вдох и выдох. Назовите адрес.",
        "Мне нужен адрес, чтобы направить помощь. Назовите адрес.",
        "Что случилось?",
        "Есть пострадавшие?",
    ):
        r = student.post(say, json={"text": text, "latency_ms": 1500})
        assert r.status_code == 200, r.text
    view = student.get(f"/api/v1/training/calls/{call['call_id']}").json()
    assert view["psy"]["profile"] == "panic" and view["psy"]["peak"] == 5
    first_op = next(m for m in view["messages"] if m["speaker"] == "operator")
    assert {"CALM_DOWN"} <= {a["code"] for a in first_op["meta"]["acts"]}
    student.post(f"/api/v1/training/calls/{call['call_id']}/end")

    services = [{"code": s["code"], "is_main": s["main"], "added_by": "auto"} for s in ref["services"]]
    saved = student.post(
        f"/api/v1/incidents/cards/{card['id']}/save",
        json={"data": fill_from_reference(ref, call["aon"]), "services": services},
    )
    assert saved.status_code == 200, saved.text
    a = student.post(f"/api/v1/assessment/cards/{card['id']}/evaluate", json={"role": "112"}).json()
    psy = a["details"]["psy"]
    keys = {c["key"]: c for c in psy["criteria"]}
    assert keys["psy_forbidden"]["score"] < 1 and any(
        "успокойтесь" in e.lower() for e in keys["psy_forbidden"]["errors"]
    )
    assert keys["psy_judge"]["score"] is None and keys["psy_voice"]["score"] is not None  # голосовой канал был
    assert psy["weight"] == 0 and a["score"] == a["details"]["role_score"]  # вес 0 — блок отдельно от итога
    assert psy["timeline"][0]["speaker"] in {"party", "operator"} and psy["stats"]["start"] == 4
    teacher.post(f"/api/v1/training/sessions/{session_id}/finish")


def test_pause_and_sensitive_warning(app_client: Callable[[], TestClient]) -> None:
    teacher, student = as_user(app_client, "teacher"), as_user(app_client, "student")
    sid = teacher.post("/api/v1/training/scenarios/generate", json={"count": 1, "groups": [1]}).json()["ids"][0]
    teacher.post(f"/api/v1/training/scenarios/{sid}/approve")
    teacher.post(f"/api/v1/training/scenarios/{sid}/psy", json={"profile": "suicidal"})
    people = {s["login"]: s["id"] for s in teacher.get("/api/v1/training/students").json()}
    session_id = _session(teacher, people["student"], {"enabled": True, "share": 0, "sensitive": ["suicidal"]})
    warned = None
    for _ in range(12):  # банк случайный: ждём сценарий с закреплённым профилем
        call = student.post("/api/v1/training/calls/incoming", json={"groups": [1]}).json()
        if call["scenario_id"] == sid:
            warned = call
            break
        student.post(f"/api/v1/training/calls/{call['call_id']}/end")
    assert warned is not None and warned["warning"] and "отказаться" in warned["warning"]
    paused = student.post(f"/api/v1/training/calls/{warned['call_id']}/pause")
    assert paused.status_code == 200 and paused.json()["status"] == "ended"
    view = student.get(f"/api/v1/training/calls/{warned['call_id']}").json()
    assert view["psy"]["paused"] is True
    admin = as_user(app_client, "admin")
    events = {e["event"] for e in admin.get("/api/v1/audit", params={"page_size": 100}).json()["items"]}
    assert "calls.paused" in events
    teacher.post(f"/api/v1/training/sessions/{session_id}/finish")
