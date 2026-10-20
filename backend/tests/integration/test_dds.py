"""П. 2.1, 2.2 через HTTP: карточка из 112 поступает в ДДС, «Получена службой», статусы, права."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.integration.test_journal import app_client as journal_app_client  # noqa: F401 — та же фикстура
from tests.integration.test_journal import as_user, new_card, start_lesson

DDS = "DDS_BASMANNYY"  # ДДС района — подбирается по адресу «Басманный»


@pytest.fixture(scope="module")
def app_client(journal_app_client: Callable[[], TestClient]) -> Iterator[Callable[[], TestClient]]:  # noqa: F811
    yield journal_app_client


@pytest.fixture(scope="module")
def lesson(app_client: Callable[[], TestClient]) -> str:
    """Идущее занятие: «student» — оператор 112, «petrov» — диспетчер ДДС района."""
    return start_lesson(app_client, dds={"petrov": DDS})


def dds_journal(c: TestClient, service: str = DDS, **params: Any) -> dict[str, Any]:
    r = c.get(f"/api/v1/incidents/dds/{service}/journal", params=params)
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


def set_status(
    c: TestClient, card_id: str, status: str, order_no: str = "", comment: str = "", service: str = DDS
) -> Any:
    return c.post(
        f"/api/v1/incidents/dds/{service}/cards/{card_id}/status",
        json={"status": status, "order_no": order_no, "comment": comment},
    )


def test_card_flows_from_112_to_dds(app_client: Callable[[], TestClient], lesson: str) -> None:
    operator = as_user(app_client, "student")
    dds = as_user(app_client, "petrov")
    card = new_card(operator, session_id=lesson)
    # черновик в ДДС не попадает
    operator.post("/api/v1/incidents/cards", json={"aon": ""})

    rows = dds_journal(dds)["items"]
    row = next(r for r in rows if r["id"] == card["id"])
    assert row["service_status"] == "added" and row["added_at"] and row["address_line"]
    assert all(r["service_status"] != "draft" for r in rows)

    view = dds.get(f"/api/v1/incidents/dds/{DDS}/cards/{card['id']}").json()
    assert view["service_status"] == "added" and view["next_statuses"] == ["accepted", "rejected"]
    assert any(s["code"] == DDS for s in view["card"]["services"]) and len(view["card"]["services"]) > 1

    assert dds.post(f"/api/v1/incidents/dds/{DDS}/cards/{card['id']}/received").json()["status"] == "received"
    assert dds.post(f"/api/v1/incidents/dds/{DDS}/cards/{card['id']}/received").json()["status"] == "received"

    assert set_status(dds, card["id"], "accepted", comment="нет наряда").status_code == 422
    assert set_status(dds, card["id"], "arrived", "1", "рано").status_code == 422
    assert set_status(dds, card["id"], "accepted", "23", "Отправлен сантехник").json()["status"] == "accepted"
    for st in ("response_started", "arrived", "works_in_progress", "works_completed"):
        assert set_status(dds, card["id"], st, comment=st).status_code == 200
    assert set_status(dds, card["id"], "works_refused", comment="поздно").status_code == 422

    services = operator.get(f"/api/v1/incidents/cards/{card['id']}").json()["services"]
    history = next(s for s in services if s["code"] == DDS)
    assert [h["status"] for h in history["history"]] == [
        "added",
        "received",
        "accepted",
        "response_started",
        "arrived",
        "works_in_progress",
        "works_completed",
    ]
    assert history["history"][2]["order_no"] == "23" and history["history"][2]["comment"] == "Отправлен сантехник"
    assert dds_journal(dds, status=["works_completed"])["total"] >= 1

    admin = as_user(app_client, "admin")
    events = admin.get("/api/v1/audit", params={"q": str(card["number"])}).json()["items"]
    assert {"Карточка получена службой (ДДС)", "Изменение статуса службы (ДДС)"} <= {e["event_title"] for e in events}


def test_rejection_needs_comment_and_is_final(app_client: Callable[[], TestClient], lesson: str) -> None:
    operator = as_user(app_client, "student")
    dds = as_user(app_client, "petrov")
    card = new_card(operator, session_id=lesson)
    assert set_status(dds, card["id"], "rejected").status_code == 422
    assert set_status(dds, card["id"], "rejected", comment="не наша территория").json()["status"] == "rejected"
    view = dds.get(f"/api/v1/incidents/dds/{DDS}/cards/{card['id']}").json()
    assert view["next_statuses"] == []


def test_visibility_and_roles(app_client: Callable[[], TestClient], lesson: str) -> None:
    operator = as_user(app_client, "student")
    card = new_card(operator, session_id=lesson)
    dds, teacher = as_user(app_client, "petrov"), as_user(app_client, "teacher")
    # служба, в которую карточка не направлялась
    assert teacher.get(f"/api/v1/incidents/dds/S104/cards/{card['id']}").status_code == 404
    # не своя служба: диспетчер занятия работает только за назначенную (ТЗ 2.7)
    assert dds.get(f"/api/v1/incidents/dds/S104/cards/{card['id']}").status_code == 403
    assert set_status(dds, card["id"], "accepted", "1", "x", service="S104").status_code == 403
    view = teacher.get(f"/api/v1/incidents/dds/{DDS}/cards/{card['id']}").json()
    assert view["next_statuses"] == []  # преподаватель смотрит, статусы ставит обучающийся
    assert set_status(teacher, card["id"], "accepted", "1", "x").status_code == 403
    admin = as_user(app_client, "admin")
    assert admin.get(f"/api/v1/incidents/dds/{DDS}/journal").status_code == 403


def test_trainee_sees_only_own_lesson_and_service(app_client: Callable[[], TestClient], lesson: str) -> None:
    """ТЗ 2.7, 2.8: код службы в адресе ничего не открывает. Обучающийся видит карточки только той службы, за которую
    отвечает в идущем занятии, и только карточки этого занятия; преподаватель — все."""
    operator, dds, teacher = (as_user(app_client, u) for u in ("student", "petrov", "teacher"))
    own = new_card(operator, session_id=lesson)
    outside = new_card(operator)  # та же служба, но карточка вне занятия
    other_lesson = start_lesson(app_client, dds={"student": DDS}, operators=())
    foreign = new_card(operator, session_id=other_lesson)  # та же служба, другое занятие

    ids = {r["id"] for r in dds_journal(dds, page_size=100)["items"]}
    assert own["id"] in ids and outside["id"] not in ids and foreign["id"] not in ids
    all_ids = {r["id"] for r in dds_journal(teacher, page_size=100)["items"]}
    assert {own["id"], outside["id"], foreign["id"]} <= all_ids  # преподаватель — как раньше

    base = f"/api/v1/incidents/dds/{DDS}"
    for card in (outside, foreign):
        assert dds.get(f"{base}/cards/{card['id']}").status_code == 404
        assert dds.post(f"{base}/cards/{card['id']}/received").status_code == 404
        assert set_status(dds, card["id"], "accepted", "1", "x").status_code == 404
        assert dds.post(f"{base}/timer", json={"paused": True, "card_id": card["id"]}).status_code == 404
        assert teacher.get(f"{base}/cards/{card['id']}").status_code == 200
    assert dds.get(f"{base}/cards/{own['id']}").status_code == 200
    assert dds.post(f"{base}/cards/{own['id']}/received").status_code == 200
    # диспетчер другого занятия той же службы видит своё и не видит чужое
    other = as_user(app_client, "student")
    assert other.get(f"{base}/cards/{foreign['id']}").status_code == 200
    assert other.get(f"{base}/cards/{own['id']}").status_code == 404

    # чужая служба и обучающийся вне роли ДДС — 403 на все маршруты
    for c, service in ((dds, "S101"), (as_user(app_client, "admin"), DDS)):
        assert c.get(f"/api/v1/incidents/dds/{service}/journal").status_code == 403
    r = dds.get("/api/v1/incidents/dds/S101/journal")
    assert r.json()["error"] == "dds_not_assigned"
    for path in ("cards/" + own["id"], "brigades"):
        assert dds.get(f"/api/v1/incidents/dds/S101/{path}").status_code == 403
    assert dds.post("/api/v1/incidents/dds/S101/timer", json={"paused": True}).status_code == 403
    assert dds.post(f"/api/v1/incidents/dds/S101/cards/{own['id']}/received").status_code == 403


def test_dds_journal_order_count_and_filter(app_client: Callable[[], TestClient], lesson: str) -> None:
    """6.1: журнал ДДС считает и сортирует по копии времени сохранения в строке службы — новые сверху."""
    operator, dds = as_user(app_client, "student"), as_user(app_client, "petrov")
    first, second = new_card(operator, session_id=lesson), new_card(operator, session_id=lesson)
    rows = dds_journal(dds, page_size=100)["items"]
    numbers = [r["number"] for r in rows]
    assert numbers.index(second["number"]) < numbers.index(first["number"])  # новые сверху
    before = dds_journal(dds, status=["added"])["total"]
    dds.post(f"/api/v1/incidents/dds/{DDS}/cards/{second['id']}/received")
    assert dds_journal(dds, status=["added"])["total"] == before - 1
    total = dds_journal(dds)["total"]
    page2 = dds_journal(dds, page_size=10, page=2)
    assert page2["total"] == total and len(page2["items"]) == max(0, min(10, total - 10))


def test_brigades_directory_and_choice(app_client: Callable[[], TestClient], lesson: str) -> None:
    """П. 5.5: справочник сил своей службы, выбор при «Принята», занятость на другой карточке, история и аудит."""
    operator = as_user(app_client, "student")
    dds = as_user(app_client, "petrov")
    first, second = new_card(operator, session_id=lesson), new_card(operator, session_id=lesson)

    options = dds.get(f"/api/v1/incidents/dds/{DDS}/brigades").json()
    codes = [o["code"] for o in options]
    assert len(codes) >= 2 and all(c.startswith(f"{DDS}:") for c in codes)
    assert options[0]["name"] and options[0]["crew"] >= 1 and options[0]["busy_card_number"] is None
    a, b = codes[0], codes[1]

    def accept(card: dict[str, Any], brigades: list[str]) -> Any:
        return dds.post(
            f"/api/v1/incidents/dds/{DDS}/cards/{card['id']}/status",
            json={"status": "accepted", "order_no": "5", "comment": "направлены силы", "brigades": brigades},
        )

    foreign = accept(first, ["S101:АЦ-11"])
    assert foreign.status_code == 422 and foreign.json()["error"] == "unknown_brigade"
    assert accept(first, [a, b]).status_code == 200

    busy = {o["code"]: o for o in dds.get(f"/api/v1/incidents/dds/{DDS}/brigades").json()}
    assert busy[a]["busy_card_number"] == first["number"]
    mine = dds.get(f"/api/v1/incidents/dds/{DDS}/brigades", params={"card_id": first["id"]}).json()
    assert all(o["busy_card_number"] is None for o in mine)  # свои силы этой карточки — не «заняты»

    taken = accept(second, [a])
    assert taken.status_code == 422 and taken.json()["error"] == "brigade_busy"
    rejected = dds.post(
        f"/api/v1/incidents/dds/{DDS}/cards/{second['id']}/status",
        json={"status": "rejected", "comment": "не наш район", "brigades": [codes[-1]]},
    )
    assert rejected.status_code == 422 and rejected.json()["error"] == "brigades_on_reject"

    view = dds.get(f"/api/v1/incidents/dds/{DDS}/cards/{first['id']}").json()
    own = next(s for s in view["card"]["services"] if s["code"] == DDS)
    assert own["brigades"] == [a, b]
    assert own["history"][-1]["brigades"] == [a.split(":", 1)[1], b.split(":", 1)[1]]

    # работы завершены — силы освобождаются и доступны другой карточке
    for st in ("response_started", "works_completed"):
        assert set_status(dds, first["id"], st, comment=st).status_code == 200
    assert accept(second, [a]).status_code == 200

    admin = as_user(app_client, "admin")
    events = admin.get("/api/v1/audit", params={"q": str(first["number"])}).json()["items"]
    assert any("силы:" in (e.get("description") or "") for e in events)


def test_brigade_busy_only_within_its_lesson(app_client: Callable[[], TestClient], lesson: str) -> None:
    """Силы у каждого занятия свои: карточка завершённого занятия, брошенная в «Принята», не держит бригаду на
    следующем занятии (на прогоне: «один отправил наряд — у второго бригады заняты»). Последний тест модуля."""
    operator, dds, teacher = (
        as_user(app_client, "student"),
        as_user(app_client, "petrov"),
        as_user(app_client, "teacher"),
    )
    code = dds.get(f"/api/v1/incidents/dds/{DDS}/brigades").json()[-1]["code"]
    old = new_card(operator, session_id=lesson)
    r = dds.post(
        f"/api/v1/incidents/dds/{DDS}/cards/{old['id']}/status",
        json={"status": "accepted", "order_no": "7", "comment": "направлены силы", "brigades": [code]},
    )
    assert r.status_code == 200, r.text
    assert teacher.post(f"/api/v1/training/sessions/{lesson}/finish").status_code == 200

    lesson2 = start_lesson(app_client, dds={"petrov": DDS})
    fresh = new_card(operator, session_id=lesson2)
    options = {
        o["code"]: o for o in dds.get(f"/api/v1/incidents/dds/{DDS}/brigades", params={"card_id": fresh["id"]}).json()
    }
    assert options[code]["busy_card_number"] is None
    r = dds.post(
        f"/api/v1/incidents/dds/{DDS}/cards/{fresh['id']}/status",
        json={"status": "accepted", "order_no": "8", "comment": "направлены силы", "brigades": [code]},
    )
    assert r.status_code == 200, r.text
