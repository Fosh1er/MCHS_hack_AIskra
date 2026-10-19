"""F6.5 п. 2 — оператор 112: вход демо-кнопкой (F2), входящий вызов, разговор потоком (F1), голосовая реплика
через заглушку распознавания, карточка с адресом из справочника, службы, сохранение, оценка с блоком
«Работа с заявителем» и источниками (F4)."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import Session, eventually
from tests.e2e.helpers import (
    PSY_ALWAYS,
    fill_card,
    finish_running_sessions,
    party_replies,
    reference,
    save_card,
    say,
    start_session,
    take_call,
)
from tests.e2e.mock_llm import STT_TEXT

pytestmark = pytest.mark.e2e


def test_operator_call_stream_card_assessment(ui: Session) -> None:
    stand = ui.stand
    # занятие с психологическим профилем у op1 — иначе модификатор (п. 3.7) не включается
    start_session(stand, [("op1", "112", None)], psy=PSY_ALWAYS)
    try:
        page = ui.new_page()
        page.goto(stand.web + "/")
        expect(page.get_by_role("note")).to_contain_text("Демонстрационный стенд")
        page.get_by_role("button", name=re.compile(r"^Войти: Оператор 112, Кузнецов")).click()
        page.wait_for_url(re.compile(r"/arm/112/journal"))

        call = take_call(page, stand)
        expect(page.locator(".call-psy")).to_contain_text("ECCS")  # шкала состояния заявителя с профилем (F4)
        before = party_replies(page).count()

        # F1: ответ печатается — курсор у растущего текста, затем строка метрик модели
        say(page, "Что у вас случилось? Назовите адрес.")
        streaming = page.locator(".call-panel .arm-msg--streaming")
        expect(streaming.locator(".arm-msg__caret")).to_be_visible()
        expect(streaming).to_contain_text("ИИ генерирует ответ")
        expect(streaming).not_to_have_count(0)
        expect(party_replies(page)).to_have_count(before + 1, timeout=30_000)
        expect(streaming).to_have_count(0)
        meta = party_replies(page).last.locator(".arm-msg__meta")
        expect(meta).to_contain_text(re.compile(r"(ИИ · e2e-mock-small · первое слово|ответ по правилам)"))

        # голосовая реплика: запись с синтетического микрофона → распознавание заглушкой → реплика в разговоре
        talk = page.locator(".call-panel__talk")
        if talk.count():
            talk.click()
            expect(talk).to_have_attribute("aria-pressed", "true")
            page.wait_for_timeout(1200)
            talk.click()
            expect(page.locator(".call-panel .arm-msg--me").filter(has_text=STT_TEXT)).to_have_count(1)
            expect(party_replies(page)).to_have_count(before + 2, timeout=30_000)
        page.locator(".call-panel__end").click()
        expect(page.locator(".call-panel__timer")).to_have_text("завершён")
        page.locator(".call-panel").get_by_role("button", name="закрыть").click()  # панель закрывает опросную карту

        fill_card(page, reference(stand, call["scenario_id"]))
        expect(page.locator(".arm-svc").first).to_be_visible()  # службы подобраны по типу, признакам и адресу
        save_card(page)
        expect(page.get_by_test_id("card-status")).to_be_visible()

        teacher = stand.client("teacher")
        eventually(
            lambda: teacher.get(f"/assessment/cards/{call['card_id']}", params={"role": "112"}).status_code == 200,
            30, what="автооценка карточки",
        )  # fmt: skip
        panel = page.get_by_label("Автооценка")
        if not panel.count():
            page.reload()
        expect(panel).to_be_visible(timeout=30_000)
        psy = page.get_by_label("Работа с заявителем")
        expect(psy).to_contain_text("Работа с заявителем в стрессе")
        expect(psy.locator(".psy-src").first).to_be_visible()  # источники методики (F4)
    finally:
        finish_running_sessions(stand)
