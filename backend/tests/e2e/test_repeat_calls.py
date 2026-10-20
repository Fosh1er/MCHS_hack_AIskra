"""ТЗ 4.6 и 6.1 в браузере: повторный звонок заявителя → баннер «Есть карточка с заявителем по этому номеру» →
«привязать» → окно связей; удержание звонка в панели разговора."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import Session
from tests.e2e.helpers import api_card_with_call, finish_running_sessions, start_session, take_call

pytestmark = pytest.mark.e2e


def test_repeat_call_banner_link_and_hold(ui: Session) -> None:
    stand = ui.stand
    client = stand.client("load001")  # отдельная учётка: занятия op1 / op2 не задеваются
    first = api_card_with_call(client, stand)  # исходная карточка по звонку — подготовка через API
    start_session(stand, [("load001", "112", None)], repeat_share=100)
    try:
        page = ui.new_page("load001")
        call = take_call(page, stand)
        assert call["aon"]
        banner = page.get_by_role("dialog", name="Совпадение с карточками")
        expect(banner).to_contain_text("Есть карточка с заявителем по этому номеру")
        expect(banner).to_contain_text(str(first["number"]))
        banner.get_by_role("button", name="привязать").click()
        expect(banner).to_have_count(0)

        panel = page.locator(".call-panel")
        panel.get_by_role("button", name="удержание").click()
        expect(panel).to_contain_text("Звонок на удержании")
        expect(page.locator(".call-panel__timer")).to_contain_text("удержание")
        panel.get_by_role("button", name="снять с удержания").click()
        expect(panel).to_contain_text("Снят с удержания")

        page.get_by_role("button", name="Связи").click()
        links = page.get_by_role("dialog", name="Связи карточки")
        expect(links).to_contain_text("Показ связей: карточек 2")
        links.get_by_role("button", name="вернуться в карточку").click()
        expect(links).to_have_count(0)
    finally:
        finish_running_sessions(stand)
