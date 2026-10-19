"""Шаги сценариев e2e, общие для нескольких тестов: вызов 112, реплика, заполнение и сохранение карточки.
Селекторы — подписи и роли интерфейса (как видит оператор), а не классы вёрстки, где это возможно."""

from __future__ import annotations

import re
from typing import Any

import httpx
from playwright.sync_api import Locator, Page, expect

from tests.e2e.conftest import Stand

CARD_URL = re.compile(r"/arm/112/[0-9a-f-]{36}")
COMPOSER = "Что вы говорите в трубку…"


def take_call(page: Page, stand: Stand) -> dict[str, Any]:
    """Журнал 112 → «учебный вызов» → «Ответить»: открыта карточка с панелью разговора. Возвращает вызов из API."""
    page.goto(f"{stand.web}/arm/112/journal")
    with page.expect_response(
        lambda r: r.url.endswith("/training/calls/incoming") and r.request.method == "POST"
    ) as rs:
        page.get_by_role("button", name="учебный вызов").click()
    call: dict[str, Any] = rs.value.json()
    assert rs.value.ok, call
    page.get_by_role("button", name="Ответить").click()
    page.wait_for_url(CARD_URL)
    expect(page.get_by_placeholder(COMPOSER)).to_be_visible()
    opened(page)
    call["card_id"] = page.url.split("/arm/112/")[1].split("?")[0]
    return call


def say(page: Page, text: str) -> None:
    box = page.get_by_placeholder(COMPOSER)
    box.fill(text)
    box.press("Enter")


def operator_lines(page: Page) -> Locator:
    return page.locator(".call-panel .arm-msg--me")


def last_line(page: Page) -> Locator:
    return page.locator(".call-panel .arm-transcript > .arm-msg").last


def wait_reply(page: Page, operator_lines_now: int, timeout: float = 30_000) -> Locator:
    """Реплика оператора в разговоре, за ней — готовый ответ собеседника (не печатающийся и не «отвечает…»).
    Ждём по последней строке разговора, а не по счётчику ответов: первая реплика заявителя приходит асинхронно."""
    expect(operator_lines(page)).to_have_count(operator_lines_now)
    reply = last_line(page)
    expect(reply).to_have_class("arm-msg arm-msg--them", timeout=timeout)
    return reply


def opened(page: Page) -> None:
    """Разговор загружен: первая реплика собеседника (приветствие, первая фраза заявителя) уже в панели —
    панель получила звонок с сервера и не перезапишет то, что оператор скажет дальше."""
    expect(page.locator(".call-panel .arm-msg--them").first).to_be_visible()


def ask(page: Page, text: str, timeout: float = 30_000) -> Locator:
    """Сказать в трубку и дождаться ответа собеседника. Возвращает строку ответа."""
    opened(page)
    n = operator_lines(page).count()
    say(page, text)
    return wait_reply(page, n + 1, timeout)


def reference(stand: Stand, scenario_id: str) -> dict[str, Any]:
    """Эталон карточки сценария — им «оператор» заполняет карточку, как в скринкасте (tools/screencast.py)."""
    r = stand.client("teacher").get(f"/training/scenarios/{scenario_id}")
    assert r.status_code == 200, r.text
    ref: dict[str, Any] = r.json()["reference_card"]
    types = stand.client("teacher").get("/dictionaries/card-types").json()
    ref["card_type_title"] = next(t["title"] for t in types if t["code"] == ref["card_types"][0])
    return ref


def fill_card(page: Page, ref: dict[str, Any]) -> None:
    """Адрес из справочника (подсказка), заявитель, «что случилось?», опросная карта, описание."""
    a = ref["address"]
    house = a["house"] + (f" к{a['building']}" if a.get("building") else "")
    page.locator("#address-line").click()
    page.locator("#address-line").press_sequentially(f"{a['street']} {a['house']}", delay=15)
    options = page.locator("[role=listbox]:visible [role=option]")
    options.first.wait_for()
    exact = options.filter(has_text=f", {house} ")
    (exact.first if exact.count() else options.first).click()
    close_map = page.get_by_label("Закрыть карту (Esc)")
    if close_map.count():  # карта открывается при выборе адреса
        page.keyboard.press("Escape")
        expect(close_map).to_have_count(0)
    page.locator("#applicant-name").fill(ref["applicant"]["name"])
    page.get_by_label("Статус заявителя").select_option(ref["applicant"]["status"])
    page.locator("#what-happened").press_sequentially(ref["card_type_title"], delay=15)
    option = page.locator("#what-happened-list [role=option]").first
    option.wait_for()
    option.click()
    for answers in (ref.get("questionnaire") or {}).values():
        form = page.locator("section.arm-q").first  # опросная карта: «ДТП» есть и среди выбранных типов выше
        for i, level in enumerate(sorted(answers)):
            row = form.locator(".arm-q__row").nth(i)
            row.get_by_role("button", name=answers[level], exact=True).click()
            expect(row.get_by_role("button", name=answers[level], exact=True)).to_have_attribute("aria-pressed", "true")
    if ref["victims"].get("has") and page.locator("#victims").get_attribute("aria-pressed") != "true":
        page.locator("#victims").click()
    page.locator("#description").fill(" ".join(ref["description_keywords"][:4]) + ", заявитель сообщает о происшествии")


def save_card(page: Page) -> None:
    page.get_by_role("button", name="сохранить", exact=True).click()
    page.get_by_role("button", name="оповестить и сохранить карточку").click()


def start_session(stand: Stand, students: list[tuple[str, str, str | None]], **settings: Any) -> str:
    """Занятие через API преподавателя (подготовка данных для теста другой роли): [(логин, роль, служба)]."""
    teacher = stand.client("teacher")
    people = {s["login"]: s["id"] for s in teacher.get("/training/students").json()}
    base = {"difficulty": 2, "call_interval_s": 600, "feed_interval_s": 600}
    r = teacher.post(
        "/training/sessions",
        json={
            "title": f"e2e: {', '.join(s[0] for s in students)}",
            "mode": "mixed" if any(s[1] == "dds" for s in students) else "cards_112",
            "card_source": "trainee",
            "groups": settings.pop("groups", []),
            "participants": [
                {"student_id": people[s], "role": role, "dds_service_code": svc} for s, role, svc in students
            ],
            "settings": {**base, **settings},
        },
    )
    assert r.status_code == 201, r.text
    sid: str = r.json()["id"]
    assert teacher.post(f"/training/sessions/{sid}/start").status_code == 200
    return sid


def finish_running_sessions(stand: Stand) -> None:
    teacher = stand.client("teacher")
    for s in teacher.get("/training/sessions", params={"limit": 100}).json()["items"]:
        if s["status"] == "running":
            teacher.post(f"/training/sessions/{s['id']}/finish")


PSY_ALWAYS = {"enabled": True, "share": 1.0, "profiles": ["panic"], "intensity": 2, "weight": 0.2, "sensitive": [],
              "llm_acts": False}  # fmt: skip


def api_card_with_call(client: httpx.Client, stand: Stand) -> dict[str, Any]:
    """Карточка 112 по учебному вызову через API (подготовка очереди ДДС): вызов, ответ, реплика, сохранение
    с автоподбором служб по эталону сценария."""
    call = client.post("/training/calls/incoming", json={}).json()
    ref = reference(stand, call["scenario_id"])
    card = client.post(
        "/incidents/cards", json={"aon": call["aon"], "channel": call["channel"], "scenario_id": call["scenario_id"]}
    ).json()
    assert client.post(f"/training/calls/{call['call_id']}/answer", json={"card_id": card["id"]}).status_code == 200
    r = client.post(f"/training/calls/{call['call_id']}/replicas", json={"text": "Что у вас случилось?"})
    assert r.status_code == 200, r.text
    client.post(f"/training/calls/{call['call_id']}/end")
    a = ref["address"]
    services = [{"code": s["code"], "is_main": s["main"], "added_by": "auto"} for s in ref["services"]]
    data = {
        "phones": {"aon": call["aon"], "provided": "", "on_site": "", "foreign": False},
        "channel": call["channel"],
        "applicant": {
            "name": ref["applicant"]["name"],
            "status": ref["applicant"]["status"],
            "foreign_language": False,
        },
        "victims": ref["victims"],
        "card_types": ref["card_types"],
        "incident_types": ref["incident_types"],
        "questionnaire": ref.get("questionnaire") or {},
        "card_flags": ref.get("card_flags", []),
        "address": {
            k: v
            for k, v in a.items()
            if v is not None and k in ("street", "house", "building", "structure", "okrug", "district", "floor", "flat")
        },
        "description": " ".join(ref["description_keywords"][:4]) + ", заявитель сообщает о происшествии",
    }
    r = client.post(f"/incidents/cards/{card['id']}/save", json={"data": data, "services": services})
    assert r.status_code == 200, r.text
    card["services"] = [s["code"] for s in services]
    card["call_id"] = call["call_id"]
    return card
