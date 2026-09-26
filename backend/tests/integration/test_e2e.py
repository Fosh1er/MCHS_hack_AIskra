"""M6 — сквозной сценарий одним тестом: вводная → карточка 112 → очередь ДДС → статусы → отчёт преподавателя.

Смешанное занятие группой, карточки для ДДС — от оператора занятия (источник «trainee»): карточка, сохранённая
оператором, должна прийти диспетчеру его службы, а отчёт — показать работу обоих.
"""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from tests.integration.test_assessment import fill_from_reference
from tests.integration.test_journal import app_client as journal_app_client  # noqa: F401
from tests.integration.test_journal import as_user

DDS = "S101"  # Служба 101 — главная служба пожаров (группа 1 классификатора)


@pytest.fixture(scope="module")
def app_client(journal_app_client: Callable[[], TestClient]) -> Iterator[Callable[[], TestClient]]:  # noqa: F811
    yield journal_app_client


def test_end_to_end_chain(app_client: Callable[[], TestClient]) -> None:
    admin, teacher = as_user(app_client, "admin"), as_user(app_client, "teacher")
    operator, dispatcher = as_user(app_client, "student"), as_user(app_client, "petrov")

    # E1: банк сценариев и группа
    ids = teacher.post("/api/v1/training/scenarios/generate", json={"count": 3, "groups": [1]}).json()["ids"]
    for sid in ids:
        teacher.post(f"/api/v1/training/scenarios/{sid}/approve")
    users = {u["login"]: u["id"] for u in admin.get("/api/v1/users").json()["items"]}
    group = {
        "name": "E2E: пожары",
        "members": [
            {"user_id": users["student"], "member_role": "112"},
            {"user_id": users["petrov"], "member_role": "dds", "dds_service_code": DDS},
        ],
    }
    assert admin.post("/api/v1/groups", json=group).status_code == 201

    # E2: занятие группой, карточки для ДДС — от оператора занятия
    g = next(x for x in teacher.get("/api/v1/groups").json() if x["name"] == "E2E: пожары")
    body = {
        "title": "Сквозной сценарий",
        "mode": "mixed",
        "card_source": "trainee",
        "groups": [1],
        "participants": [
            {"student_id": m["user_id"], "role": m["member_role"], "dds_service_code": m["dds_service_code"]}
            for m in g["members"]
        ],
    }
    session_id = teacher.post("/api/v1/training/sessions", json=body).json()["id"]
    assert teacher.post(f"/api/v1/training/sessions/{session_id}/start").json()["status"] == "running"
    lesson = operator.get("/api/v1/training/sessions/my").json()
    assert lesson["role"] == "112" and lesson["session_id"] == session_id
    # системных карточек нет: ДДС ждёт карточки оператора
    assert "операторов" in dispatcher.post("/api/v1/training/sessions/feed").json()["reason"]

    # E3: учебный вызов в категориях занятия, разговор с ИИ-заявителем
    call = operator.post(
        "/api/v1/training/calls/incoming",
        json={"groups": lesson["groups"], "difficulty": lesson["settings"]["difficulty"]},
    ).json()
    ref = teacher.get(f"/api/v1/training/scenarios/{call['scenario_id']}").json()["reference_card"]
    assert ref["incident_types"][0].startswith("1") and DDS in {s["code"] for s in ref["services"]}
    card = operator.post(
        "/api/v1/incidents/cards",
        json={"aon": call["aon"], "scenario_id": call["scenario_id"], "session_id": session_id},
    ).json()
    first = operator.post(f"/api/v1/training/calls/{call['call_id']}/answer", json={"card_id": card["id"]}).json()
    assert first and first["text"]
    for q in ("Назовите адрес", "Что случилось?", "Есть пострадавшие?"):
        assert operator.post(f"/api/v1/training/calls/{call['call_id']}/replicas", json={"text": q}).json()["text"]

    # E4: карточка сохранена, службы — по автоподбору (эталон)
    services = [{"code": s["code"], "is_main": s["main"], "added_by": "auto"} for s in ref["services"]]
    saved = operator.post(
        f"/api/v1/incidents/cards/{card['id']}/save",
        json={"data": fill_from_reference(ref, call["aon"]), "services": services},
    )
    assert saved.status_code == 200, saved.text
    operator.post(f"/api/v1/training/calls/{call['call_id']}/end")

    # E5: карточка — в очереди ДДС диспетчера занятия
    rows = dispatcher.get(f"/api/v1/incidents/dds/{DDS}/journal", params={"page_size": 50}).json()["items"]
    row = next(r for r in rows if r["id"] == card["id"])
    assert row["service_status"] == "added"
    mon = teacher.get(f"/api/v1/training/sessions/{session_id}/monitor").json()
    progress = {r["participant"]["role"]: r["progress"] for r in mon["rows"]}
    assert progress["112"]["cards_done"] == 1 and progress["dds"]["waiting"] == 1

    # E6: статусы до «Работы завершены» и звонок старшему группы
    base = f"/api/v1/incidents/dds/{DDS}/cards/{card['id']}"
    assert dispatcher.post(f"{base}/received").json()["status"] == "received"
    steps = [
        ("accepted", "15", "Выслан расчёт"),
        ("response_started", "", "Расчёт выехал"),
        ("arrived", "", "Прибыли на место"),
        ("works_in_progress", "", "Тушение"),
        ("works_completed", "", "Пожар ликвидирован"),
    ]
    for status, order_no, comment in steps:
        r = dispatcher.post(f"{base}/status", json={"status": status, "order_no": order_no, "comment": comment})
        assert r.status_code == 200, r.text
    brigade = dispatcher.post(
        "/api/v1/training/calls/dds", json={"card_id": card["id"], "service_code": DDS, "party": "brigade"}
    ).json()
    dispatcher.post(f"/api/v1/training/calls/{brigade['call_id']}/replicas", json={"text": "Доложите обстановку"})
    dispatcher.post(f"/api/v1/training/calls/{brigade['call_id']}/end")

    # E7: мониторинг, завершение, оценка всех карточек
    mon = teacher.get(f"/api/v1/training/sessions/{session_id}/monitor").json()
    progress = {r["participant"]["role"]: r["progress"] for r in mon["rows"]}
    assert progress["dds"]["cards_done"] == 1 and progress["dds"]["waiting"] == 0
    assert teacher.post(f"/api/v1/training/sessions/{session_id}/finish").json()["status"] == "finished"
    summary = teacher.post(f"/api/v1/assessment/sessions/{session_id}/evaluate").json()
    assert summary["assessed"] == 2 and summary["skipped"] == 0

    # E8: отчёт по обоим, экспертная правка, свои результаты у обучающихся
    report = teacher.get(f"/api/v1/assessment/sessions/{session_id}/report").json()
    by_role = {s["role"]: s for s in report["students"]}
    op_card, dds_card = by_role["112"]["cards"][0], by_role["dds"]["cards"][0]
    assert op_card["card_number"] == dds_card["card_number"] == card["number"]
    assert op_card["score"] >= 90 and op_card["processing_s"] is not None
    assert dds_card["score"] >= 70 and dds_card["passed"], dds_card["errors"]
    r = teacher.post(
        f"/api/v1/assessment/{dds_card['assessment_id']}/override",
        json={"score": 95, "comment": "Чёткие доклады, наряд указан сразу"},
    )
    assert r.status_code == 200 and r.json()["grader"] == "expert"
    mine = dispatcher.get(f"/api/v1/assessment/sessions/{session_id}/mine").json()
    assert mine["report"]["students"][0]["cards"][0]["expert_comment"] == "Чёткие доклады, наряд указан сразу"
    assert (
        operator.get(f"/api/v1/assessment/sessions/{session_id}/mine").json()["report"]["students"][0]["role"] == "112"
    )
    csv = teacher.get(f"/api/v1/assessment/sessions/{session_id}/report.csv").text
    assert csv.count(str(card["number"])) == 2  # строка оператора и строка диспетчера
