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
