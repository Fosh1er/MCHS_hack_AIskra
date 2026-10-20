"""П. 5.3: пауза таймера решения ДДС на время подсказок — по карточке или по всем карточкам службы в очереди."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.integration.test_dds import DDS, dds_journal, set_status
from tests.integration.test_journal import app_client as journal_app_client  # noqa: F401 — та же фикстура
from tests.integration.test_journal import as_user, new_card, start_lesson

TIMER = f"/api/v1/incidents/dds/{DDS}/timer"


@pytest.fixture(scope="module")
def app_client(journal_app_client: Callable[[], TestClient]) -> Iterator[Callable[[], TestClient]]:  # noqa: F811
    yield journal_app_client


@pytest.fixture(scope="module")
def lesson(app_client: Callable[[], TestClient]) -> str:
    return start_lesson(app_client, dds={"petrov": DDS})


def row(dds: TestClient, card_id: str) -> dict[str, Any]:
    return next(r for r in dds_journal(dds, page_size=100)["items"] if r["id"] == card_id)


def test_pause_one_card(app_client: Callable[[], TestClient], lesson: str) -> None:
    card = new_card(as_user(app_client, "student"), session_id=lesson)
    dds = as_user(app_client, "petrov")

    assert dds.post(TIMER, json={"paused": True, "card_id": card["id"]}).json() == {"cards": 1}
    assert row(dds, card["id"])["pause_started_at"] is not None
    assert dds.post(TIMER, json={"paused": False, "card_id": card["id"]}).json() == {"cards": 1}
    r = row(dds, card["id"])
    assert r["pause_started_at"] is None and r["paused_ms"] >= 0

    admin = as_user(app_client, "admin")
    audit = admin.get("/api/v1/audit", params={"event": "dds.timer_paused"}).json()
    assert any(i["card_number"] == card["number"] for i in audit["items"])


def test_decision_ends_pause_and_no_pause_after_decision(app_client: Callable[[], TestClient], lesson: str) -> None:
    card = new_card(as_user(app_client, "student"), session_id=lesson)
    dds = as_user(app_client, "petrov")
    dds.post(TIMER, json={"paused": True, "card_id": card["id"]})
    assert set_status(dds, card["id"], "accepted", "7", "Направлен расчёт").status_code == 200
    assert row(dds, card["id"])["pause_started_at"] is None  # решение закрыло паузу

    r = dds.post(TIMER, json={"paused": True, "card_id": card["id"]})
    assert r.status_code == 422 and r.json()["error"] == "dds_decided"


def test_pause_whole_queue(app_client: Callable[[], TestClient], lesson: str) -> None:
    operator = as_user(app_client, "student")
    first, second = new_card(operator, session_id=lesson), new_card(operator, session_id=lesson)
    outside = new_card(operator)  # та же служба, но вне занятия — не очередь диспетчера (ТЗ 2.7)
    dds, teacher = as_user(app_client, "petrov"), as_user(app_client, "teacher")

    paused = dds.post(TIMER, json={"paused": True}).json()["cards"]
    assert paused >= 2  # все карточки службы в занятии, ждущие решения
    assert row(dds, first["id"])["pause_started_at"] and row(dds, second["id"])["pause_started_at"]
    rows = dds_journal(teacher, page_size=100)["items"]
    assert next(r for r in rows if r["id"] == outside["id"])["pause_started_at"] is None
    assert dds.post(TIMER, json={"paused": False}).json()["cards"] == paused
    assert row(dds, first["id"])["pause_started_at"] is None


def test_teacher_cannot_pause(app_client: Callable[[], TestClient], lesson: str) -> None:
    teacher = as_user(app_client, "teacher")
    assert teacher.post(TIMER, json={"paused": True}).status_code == 403
