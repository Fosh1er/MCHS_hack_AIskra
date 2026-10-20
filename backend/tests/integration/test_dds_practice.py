"""ТЗ 2.7, 2.8 и демо-стенд: вне занятия обучающийся тренируется в АРМ ДДС любой службы, но видит только карточки,
не привязанные к занятиям; карточки занятий (своих и чужих) код службы в адресе не открывает."""

import asyncio
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aiskra.cli import create_user
from aiskra.main import create_app
from aiskra.shared.security import Role
from tests.integration.conftest import PASSWORD, create_schema, login, make_settings, seed_users
from tests.integration.test_journal import as_user, new_card, start_lesson

DDS = "DDS_BASMANNYY"


@pytest.fixture(scope="module")
def app_client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Callable[[], TestClient]]:
    settings = make_settings(Path(tmp_path_factory.mktemp("db")) / "practice.db")
    create_schema(settings.database_url)
    seed_users(settings)
    for login_, name in (("petrov", "Петров Пётр"), ("sidorov", "Сидоров Семён")):
        asyncio.run(
            create_user(
                settings, login=login_, full_name=name, role=Role.STUDENT, password=PASSWORD, operator_number="9"
            )
        )
    app = create_app(settings)
    with TestClient(app) as first:
        login(first, "admin")
        assert first.post("/api/v1/dictionaries/import").status_code == 200
        yield lambda: TestClient(app)


def test_free_practice_outside_lesson(app_client: Callable[[], TestClient]) -> None:
    operator, free = as_user(app_client, "student"), as_user(app_client, "sidorov")
    outside = new_card(operator)  # карточка вне занятия — общий учебный поток
    lesson = start_lesson(app_client, dds={"petrov": DDS})
    in_lesson = new_card(operator, session_id=lesson)
    base = f"/api/v1/incidents/dds/{DDS}"

    r = free.get(f"{base}/journal", params={"page_size": 100})
    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()["items"]}
    assert outside["id"] in ids and in_lesson["id"] not in ids
    assert free.get(f"{base}/cards/{outside['id']}").status_code == 200
    assert free.get(f"{base}/cards/{in_lesson['id']}").status_code == 404  # карточка занятия — не для практики
    assert free.post(f"{base}/cards/{outside['id']}/received").status_code == 200
    assert free.get("/api/v1/incidents/dds/S101/journal").status_code == 200  # вне занятия — любая служба

    petrov = as_user(app_client, "petrov")  # на занятии — только своя служба и карточки своего занятия
    assert petrov.get("/api/v1/incidents/dds/S101/journal").json()["error"] == "dds_not_assigned"
    assert petrov.get(f"{base}/cards/{outside['id']}").status_code == 404
    assert petrov.get(f"{base}/cards/{in_lesson['id']}").status_code == 200
