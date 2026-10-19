"""F6.5 п. 6 — отказы: модель недоступна → ответ «по правилам», звонок идёт; синтез недоступен → озвучка браузером
без ошибки на экране; перезапуск backend посреди звонка → после перезапуска звонок открывается и продолжается."""

from __future__ import annotations

import uuid

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import Session
from tests.e2e.helpers import ask, last_line, take_call

pytestmark = pytest.mark.e2e


def test_model_down_rules_reply(ui: Session) -> None:
    stand, mock = ui.stand, ui.stand.mock
    page = ui.new_page("load002")
    mock.stop()  # модель-заглушка остановлена: порт закрыт, как у упавшего сервера
    try:
        take_call(page, stand)
        reply = ask(page, f"Сколько людей в квартире? Проверка {uuid.uuid4().hex[:6]}")  # уникально — мимо кеша
        expect(reply.locator(".arm-msg__meta")).to_contain_text("ответ по правилам")
        expect(page.locator(".call-panel__err")).to_have_count(0)
        ask(page, "Назовите адрес, пожалуйста.")  # звонок продолжается
    finally:
        mock.start()


def test_tts_down_browser_voice_no_error(ui: Session) -> None:
    stand, mock = ui.stand, ui.stand.mock
    ui.errors.allow(r"HTTP 503 GET .*/training/calls/.*/(speak|audio)")  # отказ синтеза — ожидаемый ответ сервера
    page = ui.new_page("load002", voice=True)
    mock.fail_tts = True
    try:
        attempts = mock.count("/audio/speech")
        take_call(page, stand)
        ask(page, f"Что горит? Проверка {uuid.uuid4().hex[:6]}")
        page.wait_for_timeout(1500)  # озвучка по фразам и реплики — запросы синтеза уже ушли и получили отказ
        assert mock.count("/audio/speech") > attempts, "озвучка не обращалась к серверному синтезу"
        expect(page.locator(".call-panel__err")).to_have_count(0)
        expect(page.get_by_role("alert")).to_have_count(0)
    finally:
        mock.fail_tts = False


def test_backend_restart_mid_call(ui: Session) -> None:
    stand = ui.stand
    page = ui.new_page("load003")
    call = take_call(page, stand)
    ask(page, "Что у вас произошло? Опишите коротко.")

    ui.errors.allow(r"HTTP 50[0234] ")  # пока backend перезапускается, прокси отвечает ошибкой — это ожидаемо
    stand.backend.restart()
    page.reload()
    page.wait_for_url(f"**/arm/112/{call['card_id']}*")
    panel = page.locator(".call-panel")
    expect(panel).to_contain_text("Что у вас произошло? Опишите коротко.")  # разговор восстановлен с сервера
    ui.errors.allowed.pop()  # события браузера за время перезапуска разобраны — дальше 5xx снова ошибка
    expect(last_line(page)).to_have_class("arm-msg arm-msg--them")  # ответ до перезапуска тоже на месте
    ask(page, "Есть ли пострадавшие?")
    expect(page.locator(".call-panel__err")).to_have_count(0)
