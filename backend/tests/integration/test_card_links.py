"""П. 1.6 (ТЗ 4.6): повторные обращения — совпадение по номеру и адресу, привязка к главной, окно связей."""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from tests.integration.test_journal import app_client as journal_app_client  # noqa: F401
from tests.integration.test_journal import as_user, journal, new_card

M = "/api/v1/incidents"


@pytest.fixture(scope="module")
def app_client(journal_app_client: Callable[[], TestClient]) -> Iterator[Callable[[], TestClient]]:  # noqa: F811
    yield journal_app_client


def test_repeat_call_match_link_and_unlink(app_client: Callable[[], TestClient]) -> None:
    student, petrov, teacher = (as_user(app_client, u) for u in ("student", "petrov", "teacher"))
    first = new_card(student)  # АОН +7 (917) 980-54-13, Новая Басманная улица, 6
    repeat = student.post(f"{M}/cards", json={"aon": "89179805413"}).json()  # тот же номер в другом виде

    by_phone = student.get(f"{M}/matches", params={"phone": "89179805413", "exclude": repeat["id"]}).json()
    assert [r["number"] for r in by_phone] == [first["number"]] and by_phone[0]["match"] == "phone"
    by_place = student.get(
        f"{M}/matches", params={"street": "Новая Басманная улица", "house": "6", "exclude": repeat["id"]}
    ).json()
    assert by_place and by_place[0]["match"] == "address"
    assert petrov.get(f"{M}/matches", params={"phone": "89179805413"}).json() == []  # чужие карточки не видны
    assert teacher.get(f"{M}/matches", params={"phone": "89179805413"}).json()  # преподаватель видит все
    assert student.get(f"{M}/matches", params={"phone": "12"}).json() == []  # не телефон

    draft_main = student.post(f"{M}/cards", json={"aon": "+7 900 000-00-00"}).json()
    r = student.post(f"{M}/cards/{repeat['id']}/link", json={"main_id": draft_main["id"]})
    assert r.status_code == 422 and r.json()["error"] == "link_draft"
    r = student.post(f"{M}/cards/{repeat['id']}/link", json={"main_id": repeat["id"]})
    assert r.status_code == 422
    assert petrov.post(f"{M}/cards/{repeat['id']}/link", json={"main_id": first["id"]}).status_code == 404

    view = student.post(f"{M}/cards/{repeat['id']}/link", json={"main_id": first["id"]}).json()
    assert view["main_id"] == first["id"] and [r["number"] for r in view["rows"]] == [first["number"], repeat["number"]]
    assert student.get(f"{M}/cards/{first['id']}/links").json()["main_id"] == first["id"]
    rows = {r["number"]: r for r in journal(student)["items"]}
    assert rows[first["number"]]["linked"]  # «Связи» в журнале — у главной

    third = new_card(student)  # привязка к подчинённой — к её главной (связь одноуровневая)
    view = student.post(f"{M}/cards/{third['id']}/link", json={"main_id": repeat["id"]}).json()
    assert view["main_id"] == first["id"] and len(view["rows"]) == 3
    blocked = student.post(f"{M}/cards/{first['id']}/link", json={"main_id": third["id"]})
    assert blocked.status_code == 422 and blocked.json()["error"] == "link_has_subordinates"

    view = student.post(f"{M}/cards/{third['id']}/link", json={"main_id": None}).json()
    assert view["main_id"] is None and view["rows"] == []
    assert len(student.get(f"{M}/cards/{first['id']}/links").json()["rows"]) == 2
    events = {
        e["event"]
        for e in as_user(app_client, "admin").get("/api/v1/audit", params={"q": str(third["number"])}).json()["items"]
    }
    assert {"card.linked", "card.unlinked"} <= events


def test_repeat_call_in_session_and_assessment(app_client: Callable[[], TestClient]) -> None:
    """ТЗ 4.6: в занятии с повторными обращениями заявитель перезванивает по своей карточке; оценка проверяет, что
    новая карточка привязана к исходной (иначе — критическая ошибка)."""
    from tests.integration.test_assessment import fill_from_reference

    teacher, student = as_user(app_client, "teacher"), as_user(app_client, "student")
    ids = teacher.post("/api/v1/training/scenarios/generate", json={"count": 1, "groups": [1]}).json()["ids"]
    teacher.post(f"/api/v1/training/scenarios/{ids[0]}/approve")
    people = {s["login"]: s["id"] for s in teacher.get("/api/v1/training/students").json()}
    body = {
        "title": "Повторные обращения",
        "mode": "cards_112",
        "card_source": "generated",
        "groups": [1],
        "participants": [{"student_id": people["student"], "role": "112"}],
        "settings": {"repeat_share": 100},
    }
    sid = teacher.post("/api/v1/training/sessions", json=body).json()["id"]
    assert teacher.post(f"/api/v1/training/sessions/{sid}/start").status_code == 200

    first_call = student.post("/api/v1/training/calls/incoming", json={}).json()  # исходного звонка ещё нет
    ref = teacher.get(f"/api/v1/training/scenarios/{first_call['scenario_id']}").json()["reference_card"]
    card = student.post(
        f"{M}/cards", json={"aon": first_call["aon"], "scenario_id": first_call["scenario_id"], "session_id": sid}
    ).json()
    student.post(f"/api/v1/training/calls/{first_call['call_id']}/answer", json={"card_id": card["id"]})
    services = [{"code": s["code"], "is_main": s["main"], "added_by": "auto"} for s in ref["services"]]
    saved = student.post(
        f"{M}/cards/{card['id']}/save", json={"data": fill_from_reference(ref, first_call["aon"]), "services": services}
    )
    assert saved.status_code == 200, saved.text
    student.post(f"/api/v1/training/calls/{first_call['call_id']}/end")

    again = student.post("/api/v1/training/calls/incoming", json={}).json()
    assert again["aon"] == first_call["aon"] and again["scenario_id"] == first_call["scenario_id"]
    card2 = student.post(
        f"{M}/cards", json={"aon": again["aon"], "scenario_id": again["scenario_id"], "session_id": sid}
    ).json()
    opening = student.post(f"/api/v1/training/calls/{again['call_id']}/answer", json={"card_id": card2["id"]}).json()
    assert "уже звонил" in opening["text"]
    assert [m["number"] for m in student.get(f"{M}/matches", params={"phone": again["aon"]}).json()] == [card["number"]]
    student.post(
        f"{M}/cards/{card2['id']}/save", json={"data": fill_from_reference(ref, again["aon"]), "services": services}
    )

    def repeat_criterion() -> dict[str, object]:
        res = student.post(f"/api/v1/assessment/cards/{card2['id']}/evaluate", json={"role": "112"}).json()
        return next(c for c in res["details"]["criteria"] if c["key"] == "repeat_link") | {"passed": res["passed"]}

    missed = repeat_criterion()
    assert missed["score"] == 0 and missed["critical"] and not missed["passed"]
    student.post(f"{M}/cards/{card2['id']}/link", json={"main_id": card["id"]})
    linked = repeat_criterion()
    assert linked["score"] == 1 and not linked["critical"]
    # третий звонок — уже не повтор: по исходной карточке перезвонили, других сохранённых нет
    third = student.post("/api/v1/training/calls/incoming", json={}).json()
    assert third["call_id"] != again["call_id"]
