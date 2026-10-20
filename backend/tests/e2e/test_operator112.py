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
    last_line,
    operator_lines,
    reference,
    save_card,
    say,
    start_session,
    take_call,
    wait_reply,
)
from tests.e2e.mock_llm import STT_TEXT

pytestmark = pytest.mark.e2e


def test_operator_call_stream_card_assessment(ui: Session) -> None:
    stand = ui.stand
    # занятие с психологическим профилем у op1 — иначе модификатор (п. 3.7) не включается
    # бытовые сценарии ДДС (группы 8, 14, 21 — demo-seed) тут ни при чём: у их типов другие опросные карты
    start_session(
        stand, [("op1", "112", None)], psy=PSY_ALWAYS, groups=[g for g in range(1, 25) if g not in (8, 14, 21)]
    )
    try:
        page = ui.new_page()
        page.goto(stand.web + "/")
        expect(page.get_by_role("note")).to_contain_text("Демонстрационный стенд")
        page.get_by_role("button", name=re.compile(r"^Войти: Оператор 112, Кузнецов")).click()
        page.wait_for_url(re.compile(r"/arm/112/journal"))

        call = take_call(page, stand)
        expect(page.locator(".call-psy")).to_contain_text("ECCS")  # шкала состояния заявителя с профилем (F4)
        # F1: ответ печатается — курсор у растущего текста, затем строка метрик модели
        n = operator_lines(page).count()
        say(page, "Что у вас случилось? Назовите адрес.")
        streaming = page.locator(".call-panel .arm-msg--streaming")
        expect(streaming.locator(".arm-msg__caret")).to_be_visible()
        expect(streaming).to_contain_text("ИИ генерирует ответ")
        reply = wait_reply(page, n + 1)
        expect(streaming).to_have_count(0)
        # ответ модели; если проверка профиля его отклонила (RF1-05) — честная подпись о замене
        expect(reply.locator(".arm-msg__meta")).to_contain_text(
            re.compile("ИИ · e2e-mock-small · первое слово|ответ модели отклонён проверкой")
        )

        # голосовая реплика: запись с синтетического микрофона → распознавание заглушкой → реплика в разговоре
        talk = page.locator(".call-panel__talk")  # кнопка есть: распознавание на сервере включено (заглушка)
        talk.click()
        expect(talk).to_have_attribute("aria-pressed", "true")
        page.wait_for_timeout(1200)
        talk.click()
        wait_reply(page, n + 2)
        expect(operator_lines(page).last).to_contain_text(STT_TEXT)
        expect(last_line(page)).to_have_class("arm-msg arm-msg--them")
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
