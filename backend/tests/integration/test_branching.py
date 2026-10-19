"""F5 через HTTP: ветвящийся сценарий от генерации до итога.

Генерация по шаблону «Пожар в квартире» → входящий вызов → реплики оператора меняют ситуацию → карточка с пожарной
охраной → «Итог ситуации» в звонке и блок `details.branch` в оценке → доклад старшего группы ДДС по пути. Таймер
ситуации (`/tick`) — через сдвиг времени ответа в базе. Повтор с теми же решениями даёт тот же итог."""

import asyncio
import sqlite3
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from aiskra.cli import create_user
from aiskra.main import create_app
from aiskra.shared.security import Role
from tests.integration.conftest import PASSWORD, create_schema, login, make_settings, seed_users
from tests.integration.test_assessment import fill_from_reference

T = "/api/v1/training"
DB: dict[str, Path] = {}


@pytest.fixture(scope="module")
def app_client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Callable[[], TestClient]]:
    path = Path(tmp_path_factory.mktemp("db")) / "branching.db"
    DB["path"] = path
    settings = make_settings(path)
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
    login(c, user, arm="3")
    return c


def shift_answer(call_id: str, seconds: float) -> None:
    """Время ответа на вызов — на `seconds` раньше: ситуация «прожила» это время (таймер без ожидания)."""
    with sqlite3.connect(DB["path"]) as db:
        when = (datetime.now(UTC) - timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S.%f")
        db.execute("UPDATE training_calls SET answered_at = ? WHERE id = ?", (when, call_id.replace("-", "")))


@pytest.fixture(scope="module")
def scenario(app_client: Callable[[], TestClient]) -> dict[str, Any]:
    teacher = as_user(app_client, "teacher")
    templates = teacher.get(f"{T}/branch-templates").json()
    assert {t["id"] for t in templates} == {"fire_flat", "cardiac_arrest", "gas_leak", "dtp_victims"}
    assert all(3 <= t["forks"] <= 5 for t in templates)
    r = teacher.post(f"{T}/scenarios/generate", json={"count": 1, "groups": [1], "branching": "fire_flat"})
    assert r.status_code == 200, r.text
    sid = r.json()["ids"][0]
    assert teacher.post(f"{T}/scenarios/{sid}/approve").status_code == 200
    view = teacher.get(f"{T}/scenarios/{sid}").json()
    assert view["incident_type_code"] in {"1050101", "1050102"}
    assert view["branching"]["id"] == "fire_flat" and view["branching"]["start"] == "start"
    assert view["legend"]["opening"].startswith("Алло! У нас пожар")
    assert {s["code"] for s in view["reference_card"]["services"]} >= {"S101"}
    assert teacher.post(f"{T}/scenarios/generate", json={"count": 1, "branching": "nope"}).status_code == 422
    return view


def incoming(
    student: TestClient, teacher: TestClient, session_id: str | None = None
) -> tuple[str, str, dict[str, Any], str]:
    call = student.post(f"{T}/calls/incoming", json={"groups": [1]}).json()
    ref = teacher.get(f"{T}/scenarios/{call['scenario_id']}").json()["reference_card"]
    body = {"aon": call["aon"], "scenario_id": call["scenario_id"], "session_id": session_id}
    card = student.post("/api/v1/incidents/cards", json=body).json()
    opening = student.post(f"{T}/calls/{call['call_id']}/answer", json={"card_id": card["id"]}).json()
    assert "У нас пожар" in opening["text"]  # профиль может окрасить первую фразу
    return call["call_id"], card["id"], ref, call["aon"]


def say(student: TestClient, call_id: str, text: str) -> dict[str, Any]:
    r = student.post(f"{T}/calls/{call_id}/replicas", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


def save_card(student: TestClient, card_id: str, ref: dict[str, Any], aon: str) -> None:
    services = [{"code": s["code"], "is_main": s["main"], "added_by": "auto"} for s in ref["services"]]
    r = student.post(
        f"/api/v1/incidents/cards/{card_id}/save", json={"data": fill_from_reference(ref, aon), "services": services}
    )
    assert r.status_code == 200, r.text


def test_good_operator_gets_favorable_outcome(app_client: Callable[[], TestClient], scenario: dict[str, Any]) -> None:
    student, teacher = as_user(app_client, "student"), as_user(app_client, "teacher")
    call_id, card_id, ref, aon = incoming(student, teacher)
    view = student.get(f"{T}/calls/{call_id}").json()
    assert view["branching"] is True and view["branch"]["node"] == "start" and view["branch"]["outcome"] is None

    say(student, call_id, "Назовите адрес")
    reply = say(student, call_id, "Выходите из квартиры с ребёнком, закройте за собой дверь, лифтом не пользуйтесь!")
    assert reply["text"].startswith("Всё, мы вышли, дверь закрыла.")  # реплика-событие узла — в начале ответа
    assert student.post(f"{T}/calls/{call_id}/tick").json() == []  # ситуация не менялась — событий нет
    save_card(student, card_id, ref, aon)
    view = student.get(f"{T}/calls/{call_id}").json()
    assert view["branch"]["final"] is False  # разговор ещё идёт — итог не окончательный
    student.post(f"{T}/calls/{call_id}/end")

    branch = student.get(f"{T}/calls/{call_id}").json()["branch"]
    assert branch["final"] is True and branch["outcome"]["code"] == "favorable"
    assert [p["node"] for p in branch["path"]] == ["start", "out", "contained"]
    start = branch["forks"][0]
    assert start["taken"]["to"] == "out" and {o["to"] for o in start["others"]} == {"trapped"}
    assert all(c["source"] in branch["sources"] for f in branch["forks"] for c in [f["taken"], *f["others"]] if c)
    assert branch["decisions"]["said:evacuate"] >= 0 and "card_saved" in branch["decisions"]

    a = student.post("/api/v1/assessment/cards/" + card_id + "/evaluate", json={"role": "112"}).json()
    block = a["details"]["branch"]
    assert block["outcome"]["code"] == "favorable" and block["score"] == 100 and block["weight"] == 0
    assert "role_score" not in a["details"]  # вес 0 — итог ситуации на балл не влияет

    # ДДС: доклад старшего группы по прибытии — по пути ситуации (люди вышли, дверь закрыта)
    petrov = as_user(app_client, "petrov")
    base = f"/api/v1/incidents/dds/S101/cards/{card_id}"
    petrov.post(f"{base}/received")
    for status in ("accepted", "response_started", "arrived"):
        r = petrov.post(f"{base}/status", json={"status": status, "order_no": "12", "comment": "Выслан наряд ПСЧ-12"})
        assert r.status_code == 200, r.text
    dds = petrov.post(f"{T}/calls/dds", json={"card_id": card_id, "service_code": "S101", "party": "brigade"}).json()
    report = say(petrov, dds["call_id"], "Доложите обстановку")["text"]
    assert report.startswith("Прибыли. Жильцы на улице, горит кухня, дверь закрыта")


def test_silence_and_bad_advice_lead_to_worse_outcomes(
    app_client: Callable[[], TestClient], scenario: dict[str, Any]
) -> None:
    student, teacher = as_user(app_client, "student"), as_user(app_client, "teacher")
    call_id, card_id, ref, aon = incoming(student, teacher)
    say(student, call_id, "Назовите адрес")
    shift_answer(call_id, 130)  # прошло 2 минуты без инструкции по эвакуации
    events = student.post(f"{T}/calls/{call_id}/tick").json()
    assert [e["text"] for e in events] == ["Мы не можем выйти — в коридоре чёрный дым! Мы в комнате, сын кашляет!"]
    assert events[0]["tone"]["changes"][0]["reason"] == "situation"  # ситуация сделала заявителя тревожнее
    reply = say(student, call_id, "Есть угроза? Что сейчас с дымом?")
    assert "чёрный дым" in reply["text"]  # заявитель рассказывает о ситуации, какой она стала (факты узла)
    reply = say(student, call_id, "Закройтесь в комнате, заткните щели мокрой тканью, закройте вентиляцию")
    assert reply["text"].startswith("Заткнула щели мокрым полотенцем")
    save_card(student, card_id, ref, aon)
    student.post(f"{T}/calls/{call_id}/end")
    branch = student.get(f"{T}/calls/{call_id}").json()["branch"]
    assert [p["node"] for p in branch["path"]] == ["start", "trapped", "sheltered", "rescued"]
    assert branch["outcome"]["code"] == "partial"

    # вредный совет: «откройте окна» — выход отрезан сразу, без инструкции укрыться — отравление
    call_id, card_id, ref, aon = incoming(student, teacher)
    reply = say(student, call_id, "Откройте окна, проветрите!")
    assert reply["text"].startswith("Мы не можем выйти")
    save_card(student, card_id, ref, aon)
    student.post(f"{T}/calls/{call_id}/end")
    branch = student.get(f"{T}/calls/{call_id}").json()["branch"]
    assert branch["outcome"]["code"] == "adverse"
    harmful = next(i for i in branch["instructions"] if i["id"] == "open_window")
    assert harmful["harmful"] is True and harmful["said_s"] is not None


def test_same_decisions_same_outcome_and_weight(app_client: Callable[[], TestClient], scenario: dict[str, Any]) -> None:
    """Повтор с теми же решениями → тот же путь; вес блока из занятия входит в итоговый балл."""
    student, teacher = as_user(app_client, "student"), as_user(app_client, "teacher")
    people = {s["login"]: s["id"] for s in teacher.get(f"{T}/students").json()}
    body = {
        "title": "Ветвление: пожары",
        "mode": "cards_112",
        "card_source": "generated",
        "groups": [1],
        "participants": [{"student_id": people["student"], "role": "112"}],
        "settings": {"branch": {"weight": 0.5}},
    }
    session_id = teacher.post(f"{T}/sessions", json=body).json()["id"]
    assert teacher.post(f"{T}/sessions/{session_id}/start").status_code == 200
    paths = []
    for _ in range(2):
        call_id, card_id, ref, aon = incoming(student, teacher, session_id)
        say(student, call_id, "Выходите из квартиры, закройте за собой дверь")
        shift_answer(call_id, 400)  # карточку сохраним «через 400 с» — позже норматива
        save_card(student, card_id, ref, aon)
        student.post(f"{T}/calls/{call_id}/end")
        branch = student.get(f"{T}/calls/{call_id}").json()["branch"]
        paths.append(([p["node"] for p in branch["path"]], branch["outcome"]["code"]))
        a = student.post(f"/api/v1/assessment/cards/{card_id}/evaluate", json={"role": "112"}).json()
        assert a["details"]["branch"]["weight"] == 0.5
        assert a["score"] == round(0.5 * a["details"]["role_score"] + 0.5 * 60, 1)  # частичный итог — 60
    assert paths[0] == paths[1] == (["start", "out", "spread"], "partial")
    assert teacher.post(f"{T}/sessions/{session_id}/finish").status_code == 200
    report = teacher.get(f"/api/v1/assessment/sessions/{session_id}/report").json()
    assert report["branch_outcomes"]["partial"] == 2
    assert [c["branch_outcome"] for s in report["students"] for c in s["cards"]] == ["partial", "partial"]


def test_plain_scenarios_unchanged_and_access(app_client: Callable[[], TestClient], scenario: dict[str, Any]) -> None:
    """Без ветвления — прежнее поведение: звонок без `branch`, таймер ничего не делает; таймер — своему звонку."""
    teacher, student, petrov = (as_user(app_client, u) for u in ("teacher", "student", "petrov"))
    sid = teacher.post(f"{T}/scenarios/generate", json={"count": 1, "groups": [2]}).json()["ids"][0]
    teacher.post(f"{T}/scenarios/{sid}/approve")
    call = student.post(f"{T}/calls/incoming", json={"groups": [2]}).json()
    student.post(f"{T}/calls/{call['call_id']}/answer", json={})
    assert student.post(f"{T}/calls/{call['call_id']}/tick").json() == []
    view = student.get(f"{T}/calls/{call['call_id']}").json()
    assert view["branching"] is False and view["branch"] is None
    assert teacher.get(f"{T}/scenarios/{sid}").json()["branching"] is None
    assert petrov.post(f"{T}/calls/{call['call_id']}/tick").status_code == 404
    assert TestClient(student.app).get(f"{T}/branch-templates").status_code == 401
    assert student.get(f"{T}/branch-templates").status_code == 403


def test_branch_with_psy_profile(app_client: Callable[[], TestClient], scenario: dict[str, Any]) -> None:
    """Ветвление вместе с психологическим профилем: событие ситуации поднимает уровень профиля, ворота узла
    объединяются с воротами профиля, реплика-событие звучит в начале ответа."""
    student, teacher = as_user(app_client, "student"), as_user(app_client, "teacher")
    people = {s["login"]: s["id"] for s in teacher.get(f"{T}/students").json()}
    body = {
        "title": "Ветвление и паника",
        "mode": "cards_112",
        "card_source": "generated",
        "groups": [1],
        "participants": [{"student_id": people["student"], "role": "112"}],
        "settings": {"psy": {"enabled": True, "share": 1, "profiles": ["panic"]}},
    }
    session_id = teacher.post(f"{T}/sessions", json=body).json()["id"]
    teacher.post(f"{T}/sessions/{session_id}/start")
    call_id, *_ = incoming(student, teacher, session_id)
    view = student.get(f"{T}/calls/{call_id}").json()
    assert view["psy"]["profile"] == "panic" and view["branching"] is True
    level = view["psy"]["level"]
    shift_answer(call_id, 130)
    reply = say(student, call_id, "Назовите адрес")
    assert reply["text"].startswith("Мы не можем выйти")  # событие пришло с репликой, раньше таймера
    after = student.get(f"{T}/calls/{call_id}").json()
    assert after["psy"]["level"] >= level and after["branch"]["node"] == "trapped"
    meta = next(m["meta"] for m in after["messages"] if m["speaker"] == "operator")
    assert meta["branch"]["node"] == "trapped" and meta["acts"]  # разметка профиля и ветвления — вместе
    teacher.post(f"{T}/sessions/{session_id}/finish")
