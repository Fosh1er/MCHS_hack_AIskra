"""F6.5 п. 3 — диспетчер ДДС: очередь → «Принята» с бригадами → звонок старшему группы → статусы до «Работы
завершены» → запись звонка (WAV) скачивается из журнала IP-телефона."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import Session
from tests.e2e.helpers import COMPOSER, api_card_with_call, ask, finish_running_sessions, start_session

pytestmark = pytest.mark.e2e
DISPATCHERS = {"S101": "dds1", "S103": "dds2"}  # демо-диспетчеры: пожарная и скорая


def set_status(page: Page, value: str, comment: str, *, order: str | None = None, brigades: int = 0) -> None:
    page.locator("button:visible", has_text="изменить статус").first.click()
    editor = page.get_by_role("dialog", name="Изменение статуса службы")
    editor.get_by_label("Статус", exact=True).select_option(value)
    if order:
        editor.get_by_placeholder("Номер наряда").fill(order)
    if brigades:
        forces = editor.locator(".dds-editor__forces input[type=checkbox]:not([disabled])")
        forces.first.wait_for()
        for i in range(brigades):
            forces.nth(i).check()
    editor.get_by_placeholder("Комментарий").fill(comment)
    editor.get_by_label("Сохранить статус").click()
    expect(editor).to_have_count(0)


def test_dds_queue_statuses_brigade_call_recording(ui: Session) -> None:
    stand = ui.stand
    # АРМ ДДС обучающемуся открыт только на занятии и только за свою службу (ТЗ 2.7, 2.8)
    finish_running_sessions(stand)
    sid = start_session(stand, [(login, "dds", code) for code, login in DISPATCHERS.items()])
    try:
        _queue_statuses_brigade_call_recording(ui, sid)
    finally:
        finish_running_sessions(stand)


def _queue_statuses_brigade_call_recording(ui: Session, sid: str) -> None:
    stand = ui.stand
    for _ in range(8):  # карточка оператора, которая придёт в службу демо-диспетчера (сценарий случайный)
        card = api_card_with_call(stand.client("op2"), stand, sid)
        SERVICE = next((s for s in DISPATCHERS if s in card["services"]), "")
        if SERVICE:
            break
    assert SERVICE, card["services"]
    login = DISPATCHERS[SERVICE]

    page = ui.new_page(login)
    page.goto(f"{stand.web}/arm/dds/{SERVICE}")
    row = page.locator(".arm-jrow", has_text=str(card["number"]))
    row.dblclick()
    page.wait_for_url(f"**/arm/dds/{SERVICE}/{card['id']}")
    dds = stand.client(login)

    def status() -> str:
        return str(dds.get(f"/incidents/dds/{SERVICE}/cards/{card['id']}").json()["service_status"])

    set_status(page, "accepted", "Высылаем отделение", order="12", brigades=1)
    assert status() == "accepted"
    view = dds.get(f"/incidents/dds/{SERVICE}/cards/{card['id']}").json()
    own = next(s for s in view["card"]["services"] if s["code"] == SERVICE)
    assert own.get("brigades"), own  # силы службы сохранены со статусом (п. 5.5)

    # IP-телефон: у демо-служб задана телефонная книга (demo_seed) — набор номера не из книги не начинает звонок,
    # звонок начальнику аварийной бригады из книги — ИИ докладывает
    page.get_by_label("Номер абонента").fill("999-99")
    page.get_by_role("button", name="вызов").click()
    expect(page.get_by_label("IP-телефон").get_by_role("alert")).to_have_text("Номер не обслуживается")
    page.get_by_role("button", name="Начальник аварийной бригады").first.click()
    box = page.get_by_placeholder(COMPOSER)
    expect(box).to_be_visible()
    ask(page, "Доложите обстановку")
    page.locator(".call-panel__end").click()
    expect(page.get_by_label("IP-телефон")).to_contain_text("линия свободна")  # звонок завершён, линия свободна

    for value, text in (
        ("response_started", "Отделение выехало"),
        ("arrived", "Прибыли на место"),
        ("works_in_progress", "Работы начаты"),
        ("works_completed", "Работы завершены"),
    ):
        set_status(page, value, text)
        assert status() == value

    # запись звонка старшему группы: WAV из журнала звонков IP-телефона
    rec = page.locator(".ipphone__logrow a", has_text="запись").first
    expect(rec).to_be_visible()
    with page.expect_download() as dl:
        rec.click()
    head = Path(dl.value.path()).read_bytes()[:12]
    assert head[:4] == b"RIFF" and head[8:12] == b"WAVE", head
