"""F6.5 — самостоятельная тренировка ДДС (п. 2.1, рекомендация экспертов п. 10): вне занятия обучающийся берёт
учебную карточку кнопкой в реестре, доводит до «Работы завершены» и сразу получает оценку с рекомендациями."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import Session
from tests.e2e.helpers import finish_running_sessions
from tests.e2e.test_dds import set_status

pytestmark = pytest.mark.e2e
SERVICE = "S101"
LOGIN = "load002"  # отдельная учётка: занятия op1 / op2 и диспетчеров dds1 / dds2 не задеваются


def test_dds_self_training_card_and_instant_assessment(ui: Session) -> None:
    stand = ui.stand
    finish_running_sessions(stand)  # на занятии кнопки нет — карточки даёт поток занятия
    page = ui.new_page(LOGIN)
    page.goto(f"{stand.web}/arm/dds/{SERVICE}")
    page.get_by_role("button", name="учебная карточка").click()
    expect(page.locator(".dds-selfnote")).to_contain_text("в очереди")

    client = stand.client(LOGIN)
    rows = client.get(f"/incidents/dds/{SERVICE}/journal", params={"page_size": 10}).json()["items"]
    card = rows[0]
    assert client.get(f"/incidents/dds/{SERVICE}/cards/{card['id']}").json()["self_training"] is True
    other = stand.client("load003").get(f"/incidents/dds/{SERVICE}/journal", params={"page_size": 100}).json()
    assert card["id"] not in {r["id"] for r in other["items"]}  # чужая учебная карточка не видна

    page.locator(".arm-jrow", has_text=str(card["number"])).dblclick()
    page.wait_for_url(f"**/arm/dds/{SERVICE}/{card['id']}")
    set_status(page, "accepted", "Выслан наряд", order="7")
    for value, text in (
        ("response_started", "Отделение выехало"),
        ("arrived", "Прибыли на место"),
        ("works_in_progress", "Работы начаты"),
        ("works_completed", "Работы завершены"),
    ):
        set_status(page, value, text)

    panel = page.get_by_label("Автооценка")
    expect(panel.locator(".assess__score")).to_be_visible()
    expect(panel.get_by_label("Рекомендации")).to_be_visible()
