"""П. 2.1, 2.2 через HTTP: карточка из 112 поступает в ДДС, «Получена службой», статусы, права."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.integration.test_journal import app_client as journal_app_client  # noqa: F401 — та же фикстура
from tests.integration.test_journal import as_user, new_card

DDS = "DDS_BASMANNYY"  # ДДС района — подбирается по адресу «Басманный»


@pytest.fixture(scope="module")
def app_client(journal_app_client: Callable[[], TestClient]) -> Iterator[Callable[[], TestClient]]:  # noqa: F811
    yield journal_app_client


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


def test_card_flows_from_112_to_dds(app_client: Callable[[], TestClient]) -> None:
    operator = as_user(app_client, "student")
    dds = as_user(app_client, "petrov")
    card = new_card(operator)
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


def test_rejection_needs_comment_and_is_final(app_client: Callable[[], TestClient]) -> None:
    operator = as_user(app_client, "student")
    dds = as_user(app_client, "petrov")
    card = new_card(operator)
    assert set_status(dds, card["id"], "rejected").status_code == 422
    assert set_status(dds, card["id"], "rejected", comment="не наша территория").json()["status"] == "rejected"
    view = dds.get(f"/api/v1/incidents/dds/{DDS}/cards/{card['id']}").json()
    assert view["next_statuses"] == []


def test_visibility_and_roles(app_client: Callable[[], TestClient]) -> None:
    operator = as_user(app_client, "student")
    card = new_card(operator)
    dds = as_user(app_client, "petrov")
    # служба, в которую карточка не направлялась
    assert dds.get(f"/api/v1/incidents/dds/S104/cards/{card['id']}").status_code == 404
    assert set_status(dds, card["id"], "accepted", "1", "x", service="S104").status_code == 404
    teacher = as_user(app_client, "teacher")
    view = teacher.get(f"/api/v1/incidents/dds/{DDS}/cards/{card['id']}").json()
    assert view["next_statuses"] == []  # преподаватель смотрит, статусы ставит обучающийся
    assert set_status(teacher, card["id"], "accepted", "1", "x").status_code == 403
    admin = as_user(app_client, "admin")
    assert admin.get(f"/api/v1/incidents/dds/{DDS}/journal").status_code == 403


def test_dds_journal_order_count_and_filter(app_client: Callable[[], TestClient]) -> None:
    """6.1: журнал ДДС считает и сортирует по копии времени сохранения в строке службы — новые сверху."""
    operator, dds = as_user(app_client, "student"), as_user(app_client, "petrov")
    first, second = new_card(operator), new_card(operator)
    rows = dds_journal(dds, page_size=100)["items"]
    numbers = [r["number"] for r in rows]
    assert numbers.index(second["number"]) < numbers.index(first["number"])  # новые сверху
    before = dds_journal(dds, status=["added"])["total"]
    dds.post(f"/api/v1/incidents/dds/{DDS}/cards/{second['id']}/received")
    assert dds_journal(dds, status=["added"])["total"] == before - 1
    total = dds_journal(dds)["total"]
    page2 = dds_journal(dds, page_size=10, page=2)
    assert page2["total"] == total and len(page2["items"]) == max(0, min(10, total - 10))


def test_brigades_directory_and_choice(app_client: Callable[[], TestClient]) -> None:
    """П. 5.5: справочник сил своей службы, выбор при «Принята», занятость на другой карточке, история и аудит."""
    operator = as_user(app_client, "student")
    dds = as_user(app_client, "petrov")
    first, second = new_card(operator), new_card(operator)

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
