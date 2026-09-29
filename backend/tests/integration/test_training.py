"""П. 3.2, 3.3, 1.4, 2.3 через HTTP: генерация сценариев, входящий вызов с ИИ-заявителем, звонки из АРМ ДДС."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.integration.test_journal import app_client as journal_app_client  # noqa: F401
from tests.integration.test_journal import as_user, new_card

DDS = "DDS_BASMANNYY"


@pytest.fixture(scope="module")
def app_client(journal_app_client: Callable[[], TestClient]) -> Iterator[Callable[[], TestClient]]:  # noqa: F811
    yield journal_app_client


def test_generate_review_and_list(app_client: Callable[[], TestClient]) -> None:
    teacher = as_user(app_client, "teacher")
    r = teacher.post("/api/v1/training/scenarios/generate", json={"count": 3, "groups": [1, 13], "difficulty": 3})
    assert r.status_code == 200, r.text
    ids = r.json()["ids"]
    assert len(ids) == 3
    s = teacher.get(f"/api/v1/training/scenarios/{ids[0]}").json()
    assert s["status"] == "draft" and s["card_type_code"] in {"101", "104"}
    assert s["reference_card"]["incident_types"][0].startswith(("1", "13"))
    assert s["legend"]["opening"] and s["reference_card"]["services"]
    assert teacher.post(f"/api/v1/training/scenarios/{ids[0]}/approve").json()["status"] == "approved"
    assert teacher.post(f"/api/v1/training/scenarios/{ids[1]}/archive").json()["status"] == "archived"
    page = teacher.get("/api/v1/training/scenarios", params={"status": "approved"}).json()
    assert page["total"] >= 1
    student = as_user(app_client, "student")
    assert student.post("/api/v1/training/scenarios/generate", json={"count": 1}).status_code == 403


def test_partial_approval_of_reference(app_client: Callable[[], TestClient]) -> None:
    """П. 3.3: одни разделы эталона приняты, другие — на доработку; правка раздела сбрасывает решение только по нему;
    все разделы приняты — сценарий утверждён."""
    teacher = as_user(app_client, "teacher")
    sid = teacher.post("/api/v1/training/scenarios/generate", json={"count": 1, "difficulty": 2}).json()["ids"][0]
    url = f"/api/v1/training/scenarios/{sid}"
    sections = [r["key"] for r in teacher.get(url).json()["review"]]
    assert sections == ["story", "applicant", "classification", "services", "dds"]

    no_comment = teacher.post(f"{url}/review", json={"sections": {"story": {"decision": "rework"}}})
    assert no_comment.status_code == 422 and no_comment.json()["error"] == "rework_comment_required"
    marks = {k: {"decision": "accepted"} for k in sections if k != "story"}
    marks["story"] = {"decision": "rework", "comment": "Первая фраза слишком спокойная для сложности"}
    r = teacher.post(f"{url}/review", json={"sections": marks}).json()
    assert r["status"] == "draft"
    by_key = {x["key"]: x for x in r["sections"]}
    assert by_key["story"]["decision"] == "rework" and "спокойная" in by_key["story"]["comment"]
    assert by_key["services"]["decision"] == "accepted"
    row = next(
        x
        for x in teacher.get("/api/v1/training/scenarios", params={"status": "draft"}).json()["items"]
        if x["id"] == sid
    )
    assert (row["review_accepted"], row["review_rework"], row["review_total"]) == (4, 1, 5)

    # правка речи заявителя: решение по «story» больше не действует, остальные разделы — приняты
    assert teacher.patch(url, json={"opening": "Алло! Помогите, тут дым из квартиры!"}).status_code == 200
    state = {x["key"]: x for x in teacher.get(url).json()["review"]}
    assert state["story"]["decision"] is None and state["story"]["stale"] is True
    assert state["dds"]["decision"] == "accepted" and state["dds"]["stale"] is False

    done = teacher.post(f"{url}/review", json={"sections": {"story": {"decision": "accepted"}}}).json()
    assert done["status"] == "approved"
    # утверждённый сценарий с разделом на доработку снимается с банка занятий
    back = teacher.post(f"{url}/review", json={"sections": {"dds": {"decision": "rework", "comment": "нужен звонок"}}})
    assert back.json()["status"] == "draft"
    assert teacher.post(f"{url}/approve").json()["status"] == "approved"  # полное утверждение принимает все разделы
    assert all(x["decision"] == "accepted" for x in teacher.get(url).json()["review"])

    bad = teacher.post(f"{url}/review", json={"sections": {"nope": {"decision": "accepted"}}})
    assert bad.status_code == 422 and bad.json()["error"] == "unknown_review_section"
    student = as_user(app_client, "student")
    assert student.post(f"{url}/review", json={"sections": {"dds": {"decision": "accepted"}}}).status_code == 403
    admin = as_user(app_client, "admin")
    titles = {e["event_title"] for e in admin.get("/api/v1/audit", params={"q": ""}).json()["items"]}
    assert "Проверка эталона по разделам (частичное утверждение)" in titles


def test_incoming_call_with_ai_applicant(app_client: Callable[[], TestClient]) -> None:
    student = as_user(app_client, "student")
    call = student.post("/api/v1/training/calls/incoming", json={}).json()
    assert call["aon"].startswith("+7") and call["scenario_id"]
    card = student.post("/api/v1/incidents/cards", json={"aon": call["aon"], "scenario_id": call["scenario_id"]}).json()
    opening = student.post(f"/api/v1/training/calls/{call['call_id']}/answer", json={"card_id": card["id"]}).json()
    assert opening["speaker"] == "party" and opening["text"]
    reply = student.post(f"/api/v1/training/calls/{call['call_id']}/replicas", json={"text": "Назовите адрес"}).json()
    assert reply["text"]
    assert student.post(f"/api/v1/training/calls/{call['call_id']}/end").json()["status"] == "ended"
    ended = student.post(f"/api/v1/training/calls/{call['call_id']}/replicas", json={"text": "алло"})
    assert ended.status_code == 422
    view = student.get(f"/api/v1/training/calls/{call['call_id']}").json()
    assert [m["speaker"] for m in view["messages"]] == ["party", "operator", "party"]
    assert view["card_id"] == card["id"]
    other = as_user(app_client, "petrov")
    assert other.get(f"/api/v1/training/calls/{call['call_id']}").status_code == 404
    teacher = as_user(app_client, "teacher")
    assert teacher.get(f"/api/v1/training/calls/{call['call_id']}").status_code == 200


def test_tone_follows_operator(app_client: Callable[[], TestClient]) -> None:
    """П. 3.6: состояние заявителя меняется от тона оператора и сохраняется у каждой его реплики."""
    student = as_user(app_client, "student")
    call = student.post("/api/v1/training/calls/incoming", json={}).json()
    card = student.post("/api/v1/incidents/cards", json={"aon": call["aon"], "scenario_id": call["scenario_id"]}).json()
    cid = call["call_id"]
    opening = student.post(f"/api/v1/training/calls/{cid}/answer", json={"card_id": card["id"]}).json()
    start = opening["tone"]["tension"]
    assert opening["message_id"] and opening["tone"]["changes"] == []

    rude = student.post(
        f"/api/v1/training/calls/{cid}/replicas", json={"text": "Успокойтесь! Быстрее говорите!"}
    ).json()
    assert [c["reason"] for c in rude["tone"]["changes"]] == ["invalidating", "pressure"]
    assert rude["tone"]["tension"] == min(10, start + 3)

    kind = student.post(f"/api/v1/training/calls/{cid}/replicas", json={"text": "Я вас слышу, где вы?"}).json()
    assert [c["reason"] for c in kind["tone"]["changes"]] == ["calming", "on_topic"]
    assert kind["tone"]["tension"] == rude["tone"]["tension"] - 2

    view = student.get(f"/api/v1/training/calls/{cid}").json()
    party = [m for m in view["messages"] if m["speaker"] == "party"]
    assert [m["tone"]["tension"] for m in party] == [start, rude["tone"]["tension"], kind["tone"]["tension"]]
    assert all(m["tone"] is None for m in view["messages"] if m["speaker"] == "operator")
    assert party[-1]["id"] == kind["message_id"] and view["tone"]["tension"] == kind["tone"]["tension"]
    assert not {"address", "applicant", "facts", "legend"} & set(view["tone"])  # фактов легенды нет
    assert view["mode"] == "text"  # реплики напечатаны (п. 3.6, R3.6-26)
    bad = student.post(f"/api/v1/training/calls/{cid}/replicas", json={"text": "Алло", "via": "telepathy"})
    assert bad.status_code == 422


def dds_call(c: TestClient, card_id: str, party: str, target: str | None = None) -> Any:
    return c.post(
        "/api/v1/training/calls/dds",
        json={"card_id": card_id, "service_code": DDS, "party": party, "target_service": target},
    )


def test_dds_calls_brigade_applicant_service(app_client: Callable[[], TestClient]) -> None:
    card = new_card(as_user(app_client, "student"))
    dds = as_user(app_client, "petrov")
    dds.post(
        f"/api/v1/incidents/dds/{DDS}/cards/{card['id']}/status",
        json={"status": "accepted", "order_no": "7", "comment": "направлен"},
    )

    brigade = dds_call(dds, card["id"], "brigade").json()
    first = dds.get(f"/api/v1/training/calls/{brigade['call_id']}").json()["messages"][0]
    assert first["text"] == "Старший группы, слушаю."
    report = dds.post(
        f"/api/v1/training/calls/{brigade['call_id']}/replicas", json={"text": "Доложите обстановку"}
    ).json()
    assert "наряд 7" in report["text"] and report["tone"] is None  # у старшего группы состояния нет

    applicant = dds_call(dds, card["id"], "applicant").json()
    assert applicant["aon"]
    ans = dds.post(
        f"/api/v1/training/calls/{applicant['call_id']}/replicas", json={"text": "Вы звонили в 112, какой адрес?"}
    ).json()
    assert "Басманная" in ans["text"]
    assert ans["tone"]["emotion"] == "calm"  # карточка без сценария — заявитель спокоен (п. 3.6)

    assert dds_call(dds, card["id"], "service", "S104").status_code in (200, 422)
    services = dds.get(f"/api/v1/incidents/dds/{DDS}/cards/{card['id']}").json()["card"]["services"]
    other = next(s["code"] for s in services if s["code"] != DDS)
    svc = dds_call(dds, card["id"], "service", other).json()
    reply = dds.post(f"/api/v1/training/calls/{svc['call_id']}/replicas", json={"text": "Карточку видите?"}).json()
    assert "видим" in reply["text"]

    calls = dds.get(f"/api/v1/training/cards/{card['id']}/calls").json()
    assert {c["party"] for c in calls} == {"brigade", "applicant", "service"}
    assert dds_call(dds, card["id"], "service", "NOPE").status_code == 422
