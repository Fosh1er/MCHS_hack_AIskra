"""Телефонная книга ДДС (п. 2.3, рекомендация экспертов) через HTTP: права, правила книги, звонки по номеру."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.integration.test_journal import app_client as journal_app_client  # noqa: F401
from tests.integration.test_journal import as_user, new_card, start_lesson

DDS = "DDS_BASMANNYY"
URL = f"/api/v1/training/dds-phonebook/{DDS}"
BOOK = [
    {"role": "head", "name": "Громов Пётр Ильич", "number": "100-01"},
    {"role": "brigade_chief", "name": "Сомов Илья Петрович", "number": "100-03"},
    {"role": "applicant", "name": "", "number": ""},
]


@pytest.fixture(scope="module")
def app_client(journal_app_client: Callable[[], TestClient]) -> Iterator[Callable[[], TestClient]]:  # noqa: F811
    yield journal_app_client


def dial(c: TestClient, card_id: str, **body: Any) -> Any:
    return c.post("/api/v1/training/calls/dds", json={"card_id": card_id, "service_code": DDS, **body})


def test_phonebook_access_and_rules(app_client: Callable[[], TestClient]) -> None:
    teacher, student = as_user(app_client, "teacher"), as_user(app_client, "student")
    empty = student.get(URL).json()  # диспетчер читает; книги нет — телефон как раньше
    assert empty["configured"] is False and empty["entries"] == [] and empty["max_entries"] == 10
    assert len(empty["roles"]) == 5

    assert student.put(URL, json={"entries": BOOK}).status_code == 403  # правит только преподаватель
    eleven = [{"role": "brigade_specialist", "name": f"Абонент {i}", "number": f"200-{i:02d}"} for i in range(11)]
    r = teacher.put(URL, json={"entries": eleven})
    assert r.status_code == 422 and "10" in r.json()["message"]
    dup = [BOOK[0], {**BOOK[1], "number": "10001"}]  # тот же номер, другая запись — повтор
    assert teacher.put(URL, json={"entries": dup}).json()["error"] == "phonebook_duplicate_number"

    saved = teacher.put(URL, json={"entries": BOOK})
    assert saved.status_code == 200, saved.text
    got = student.get(URL).json()
    assert got["configured"] is True
    assert [e["title"] for e in got["entries"]] == [
        "Руководитель организации",
        "Начальник аварийной бригады",
        "Заявитель (номер из карточки)",
    ]


def test_calls_by_phonebook(app_client: Callable[[], TestClient]) -> None:
    teacher = as_user(app_client, "teacher")
    assert teacher.put(URL, json={"entries": BOOK}).status_code == 200
    lesson = start_lesson(app_client, dds={"petrov": DDS}, operators=())
    card = new_card(as_user(app_client, "student"), session_id=lesson)
    dds = as_user(app_client, "petrov")

    head = dial(dds, card["id"], party="brigade", number="100 01").json()
    view = dds.get(f"/api/v1/training/calls/{head['call_id']}").json()
    assert view["party"] == "brigade" and view["contact"]["title"] == "Руководитель организации"
    assert view["messages"][0]["text"] == "Руководитель организации, Громов, слушаю."
    reply = dds.post(f"/api/v1/training/calls/{head['call_id']}/replicas", json={"text": "Доложите"}).json()
    assert reply["text"].startswith("Руководитель организации Громов Пётр Ильич.")
    dds.post(f"/api/v1/training/calls/{head['call_id']}/end")

    stranger = dial(dds, card["id"], party="brigade", number="999-99")
    assert stranger.status_code == 422 and stranger.json()["message"] == "Номер не обслуживается"

    applicant = dial(dds, card["id"], party="applicant").json()  # «заявитель» в книге есть — звонок идёт
    assert applicant["aon"]
    dds.post(f"/api/v1/training/calls/{applicant['call_id']}/end")
    by_number = dial(dds, card["id"], party="brigade", number=applicant["aon"]).json()
    assert dds.get(f"/api/v1/training/calls/{by_number['call_id']}").json()["party"] == "applicant"
    dds.post(f"/api/v1/training/calls/{by_number['call_id']}/end")

    # без записи «заявитель» звонить ему нельзя ни клавишей, ни набором номера из карточки
    assert teacher.put(URL, json={"entries": BOOK[:2]}).status_code == 200
    assert dial(dds, card["id"], party="applicant").json()["error"] == "applicant_not_in_book"
    assert dial(dds, card["id"], party="brigade", number=applicant["aon"]).status_code == 422

    # книга очищена — телефон как раньше: старший группы и заявитель, номер не принимается
    assert teacher.put(URL, json={"entries": []}).status_code == 200
    assert dial(dds, card["id"], party="applicant").status_code == 200
    assert dial(dds, card["id"], party="brigade", number="100-01").status_code == 422
