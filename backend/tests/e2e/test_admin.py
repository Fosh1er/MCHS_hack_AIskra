"""F6.5 п. 4 — администратор: вход паролем, оповещения, резервная копия, пользователи, группы, настройки занятия,
остановка и запуск подсистемы (поток учебных вызовов), восстановление из копии."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import Session

pytestmark = pytest.mark.e2e
NEW_LOGIN = "e2e_new_student"
NEW_NAME = "Проверкин Тест Тестович"
GROUP = "e2e-группа"
STREAM = "Поток учебных вызовов 112: 1 — работает, 0 — остановлен"
NORM = "Норматив карточки 112, с"


def login_form(page: Page, web: str, login: str, password: str) -> None:
    page.goto(f"{web}/")
    page.get_by_label("логин").fill(login)
    page.locator("input[type=password]").fill(password)
    page.get_by_role("button", name="ВОЙТИ", exact=True).click()
    page.wait_for_url(f"{web}/admin")


def set_setting(page: Page, section: str, label: str, value: str) -> None:
    card = page.locator(".cab-card", has_text=section)
    card.get_by_label(label).fill(value)
    card.get_by_role("button", name="сохранить").click()
    expect(card.get_by_text("сохранено, изменение в аудите")).to_be_visible()


def test_admin_users_groups_settings_backup_restore_alerts(ui: Session) -> None:
    stand = ui.stand
    page = ui.new_page()
    login_form(page, stand.web, "admin", stand.admin_password)
    expect(page.get_by_text("База данных")).to_be_visible()

    # резервная копия: создаётся, оповещение «копий ещё нет» уходит
    page.get_by_role("link", name="Настройки и копии").click()
    backups = page.locator(".cab-card", has_text="Резервные копии")
    backups.get_by_role("button", name="создать копию").click()
    banner = backups.get_by_text(re.compile(r"^Копия \S+: таблиц"))
    expect(banner).to_be_visible()
    name = re.match(r"Копия (\S+):", banner.inner_text()).group(1)  # type: ignore[union-attr]
    expect(backups.locator("tr", has_text=name)).to_be_visible()
    page.get_by_role("link", name="Состояние").click()
    expect(page.get_by_text("Резервные копии: копий ещё нет")).to_have_count(0)

    # пользователь
    page.get_by_role("link", name="Пользователи").click()
    page.get_by_role("button", name="пользователь").click()
    form = page.locator(".cab-card", has_text="Новый пользователь")
    form.get_by_label("Логин").fill(NEW_LOGIN)
    form.get_by_label("ФИО").fill(NEW_NAME)
    form.get_by_label("Пароль (от 8 символов)").fill(stand.password)
    form.get_by_role("button", name="создать").click()
    expect(page.locator("tr", has_text=NEW_LOGIN)).to_be_visible()

    # группа с новым пользователем
    page.get_by_role("link", name="Группы").click()
    page.get_by_role("button", name="группа").click()
    editor = page.locator(".cab-card", has_text="Новая группа")
    editor.get_by_label("Название").fill(GROUP)
    editor.get_by_label(f"В группе: {NEW_NAME}").check()
    editor.get_by_role("button", name="сохранить").click()
    expect(page.locator("tr", has_text=GROUP)).to_contain_text(NEW_NAME)

    # настройки: норматив занятия и остановка потока учебных вызовов
    page.get_by_role("link", name="Настройки и копии").click()
    set_setting(page, "Занятие по умолчанию", NORM, "90")
    set_setting(page, "Сервисы тренажёра", STREAM, "0")
    r = stand.client("load003").post("/training/calls/incoming", json={})
    assert r.status_code == 422 and "остановлен" in r.json()["message"], r.text
    set_setting(page, "Сервисы тренажёра", STREAM, "1")
    assert stand.client("load003").post("/training/calls/incoming", json={}).status_code == 200

    # восстановление: всё созданное после копии пропадает, все выходят из системы
    row = backups.locator("tr", has_text=name)
    row.get_by_role("button", name="восстановить").click()
    backups.get_by_label("Для подтверждения введите «ВОССТАНОВИТЬ»").fill("ВОССТАНОВИТЬ")
    backups.locator(".tch-override").get_by_role("button", name="восстановить").click()
    page.wait_for_url(f"{stand.web}/")
    login_form(page, stand.web, "admin", stand.admin_password)
    page.get_by_role("link", name="Пользователи").click()
    expect(page.locator("tr", has_text="op1")).to_be_visible()
    expect(page.locator("tr", has_text=NEW_LOGIN)).to_have_count(0)
    page.get_by_role("link", name="Группы").click()
    expect(page.locator("tr", has_text="Смена 1 (демо)")).to_be_visible()
    expect(page.locator("tr", has_text=GROUP)).to_have_count(0)
    page.get_by_role("link", name="Настройки и копии").click()
    expect(page.locator(".cab-card", has_text="Занятие по умолчанию").get_by_label(NORM)).not_to_have_value("90")
