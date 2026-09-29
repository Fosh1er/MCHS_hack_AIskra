"""Скриншоты для руководств пользователя (docs/manuals): преподаватель и обучающийся.

Стенд — копия рабочей базы с демо-историей (`make demo-seed`, `tools/demo_history.py`) и идущим занятием. Скрипт
сам готовит отзывы преподавателя (п. 4.7) и проходит экраны ролей в Chrome с машины (Playwright). Запуск из backend:

    AISKRA_DEMO_PASSWORD=… uv run --with playwright --with httpx python ../docs/manuals/shoot.py \\
        --web http://localhost:5174 [--only teacher|student]
"""

from __future__ import annotations

import argparse
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx
from playwright.sync_api import Page, sync_playwright

IMG = Path(__file__).parent / "img"
VIEW = {"width": 1440, "height": 900}
ONBOARDING = """(action) => fetch('/api/v1/auth/onboarding', {
  method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({action})
}).then((r) => r.status)"""


def api(base: str, user: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=f"{base}/api/v1", timeout=60)
    c.post("/auth/login", json={"login": user, "password": password}).raise_for_status()
    return c


class Shooter:
    def __init__(self, browser: Any, web: str, password: str) -> None:
        self.browser, self.web, self.password = browser, web, password
        self.ctx: Any = None
        self.page: Page | None = None
        self.failed: list[str] = []

    @property
    def p(self) -> Page:
        assert self.page is not None
        return self.page

    def login(self, user: str, arm: str = "", *, tours: bool = False, shot: str = "") -> None:
        if self.ctx is not None:
            self.ctx.close()
        self.ctx = self.browser.new_context(viewport=VIEW, locale="ru-RU", timezone_id="Europe/Moscow")
        self.page = self.ctx.new_page()
        self.p.set_default_timeout(10_000)
        self.p.on("dialog", lambda d: d.accept())
        self.p.goto(f"{self.web}/")
        self.p.wait_for_load_state("networkidle")
        self.p.get_by_label("логин").fill(user)
        self.p.locator("input[type=password]").fill(self.password)
        if arm:
            self.p.get_by_label("номер АРМ").fill(arm)
        if shot:
            self.shot(shot)
        self.p.get_by_role("button", name="ВОЙТИ").click()
        self.p.wait_for_url(
            lambda u: u.rstrip("/") != self.web.rstrip("/"), timeout=15_000
        )  # вход — уход со страницы входа
        self.p.wait_for_load_state("networkidle")
        # подсказки (п. 5.3, 5.4) показываются отдельным снимком, на остальных они перекрыли бы экран
        self.p.evaluate(ONBOARDING, "reset" if tours else "dismiss")
        self.p.reload()
        self.p.wait_for_load_state("networkidle")
        time.sleep(1)

    def go(self, path: str, wait: float = 1.2) -> None:
        self.p.goto(f"{self.web}{path}")
        self.p.wait_for_load_state("networkidle")
        time.sleep(wait)

    def shot(self, name: str, target: Any = None, *, full: bool = False) -> None:
        time.sleep(0.5)
        path = IMG / f"{name}.jpg"
        if target is not None:
            target.screenshot(path=str(path), type="jpeg", quality=88)
        else:
            self.p.screenshot(path=str(path), type="jpeg", quality=88, full_page=full)
        print("снимок", path.name, flush=True)

    def step(self, name: str, fn: Any) -> None:
        try:
            fn()
        except Exception as e:  # снимок не получился — остальные делаем
            self.failed.append(name)
            print(f"пропущено «{name}»: {type(e).__name__}: {str(e).splitlines()[0][:200]}", flush=True)
            if self.page is not None:
                self.p.screenshot(path=str(IMG / f"_fail_{name}.png"))

    def scroll_to(self, selector: str, block: str = "start") -> None:
        self.p.locator(selector).first.evaluate(f"el => el.scrollIntoView({{block: '{block}'}})")
        time.sleep(0.6)


def prepare(base: str, password: str) -> dict[str, Any]:
    """Отзывы преподавателя обучающейся op2 по двум занятиям демо-истории: второй черновик покажет прошлый отзыв."""
    teacher = api(base, "teacher", password)
    sessions = teacher.get("/training/sessions", params={"limit": 100}).json()["items"]
    by_title = {s["title"]: s["id"] for s in sessions}
    people = {s["login"]: s["id"] for s in teacher.get("/training/students").json()}
    s5 = by_title["Смена 1 (демо-история): занятие 5"]
    s6 = by_title["Смена 1 (демо-история): занятие 6"]
    running = next(s["id"] for s in sessions if s["status"] == "running")
    url = f"/assessment/sessions/{s5}/students/{people['op2']}/feedback"
    draft = teacher.post(f"{url}/draft").json()
    teacher.put(url, json={"text": draft["text"], "draft_text": draft["text"], "draft_source": draft["source"]})
    # карточка «Отработана» — у неё в журнале преподавателя кнопки «Проверена» и «Вернуть на доработку»
    op2 = api(base, "op2", password)
    rows = op2.get("/incidents/journal", params={"page": 1, "page_size": 30}).json()["items"]
    if not any(r["display_status"] == "worked" for r in rows):
        card = next((r for r in rows if r["display_status"] == "registered" and not r["empty_call"]), None)
        if card:
            op2.post(f"/incidents/cards/{card['id']}/worked", json={"comment": ""}).raise_for_status()
    return {"s5": s5, "s6": s6, "running": running, "people": people, "sessions": sessions, "teacher": teacher}


def teacher_part(sh: Shooter, d: dict[str, Any]) -> None:
    p = lambda: sh.p  # noqa: E731
    sh.login("teacher", shot="t01_login", tours=True)
    sh.step("t02_welcome", lambda: (p().get_by_text("Шаг 1 из").wait_for(), sh.shot("t02_welcome")))
    sh.p.evaluate(ONBOARDING, "dismiss")
    sh.go("/teacher")
    sh.shot("t03_home")

    sh.go("/teacher/scenarios")
    sh.shot("t04_scenarios")

    def scenario() -> None:
        p().locator(".cab-table tbody tr").first.click()
        time.sleep(1.5)
        sh.shot("t05_scenario")

    sh.step("t05_scenario", scenario)

    sh.go("/teacher/sessions")
    sh.shot("t06_sessions")

    def new_session() -> None:
        p().get_by_role("button", name="новое занятие").click()
        time.sleep(1.5)
        sh.shot("t07_session_new")

    sh.step("t07_session_new", new_session)

    sh.go(f"/teacher/sessions/{d['running']}", 2)
    sh.shot("t08_monitor")

    report = f"/teacher/sessions/{d['s6']}/report"
    sh.go(report, 1.5)
    sh.shot("t09_report")

    def expand() -> None:
        p().locator("tr[aria-expanded]", has_text="Волкова").first.click()
        time.sleep(0.8)
        sh.scroll_to("tr[aria-expanded='true']")

    def override() -> None:
        expand()
        p().get_by_role("button", name="правка").first.click()
        time.sleep(0.6)
        sh.shot("t10_report_student")

    sh.step("t10_report_student", override)

    def feedback() -> None:
        sh.go(report, 1.5)
        expand()
        p().get_by_role("button", name=re.compile("^предложить")).first.click()
        p().locator(".tch-feedback textarea").wait_for()
        time.sleep(0.6)
        box = p().locator(".tch-feedback summary")
        if box.count():
            box.first.click()
        sh.scroll_to(".tch-feedback")
        sh.shot("t11_feedback_draft")
        p().get_by_role("button", name="сохранить отзыв").click()
        time.sleep(1.2)
        sh.scroll_to(".tch-feedback", "center")
        sh.shot("t12_feedback_saved")

    sh.step("t11_feedback", feedback)

    def heatmap() -> None:
        sh.go(report, 1.5)
        sh.scroll_to("[data-tour='t-heatmap']")
        sh.shot("t13_heatmap")

    sh.step("t13_heatmap", heatmap)

    def talk() -> None:
        panic = next((s["id"] for s in d["sessions"] if s["title"].startswith("Урок: паникующий")), None)
        sh.go(f"/teacher/sessions/{panic}/report", 1.5)
        p().locator("tr[aria-expanded]").first.click()
        time.sleep(0.6)
        p().get_by_role("button", name="разговор").first.click()
        time.sleep(1.5)
        sh.scroll_to("tr[aria-expanded='true']")
        sh.shot("t14_call_review")

    sh.step("t14_call_review", talk)

    sh.go(f"/teacher/sessions/{d['s6']}/debrief", 1.5)
    sh.shot("t15_debrief")
    sh.go("/teacher/analytics", 1.5)
    sh.shot("t16_analytics")
    sh.go(f"/teacher/students/{d['people']['op2']}", 1.5)
    sh.shot("t17_profile")
    sh.go("/teacher/readiness", 1.5)
    sh.shot("t18_readiness")
    sh.go("/teacher/readiness/protocol", 1.5)
    sh.shot("t19_protocol")
    sh.go("/teacher/validation", 2)
    sh.shot("t20_validation")
    sh.go("/teacher/materials", 1.5)
    sh.shot("t21_materials")

    sh.go("/arm/112/journal", 2)
    sh.shot("t22_journal")

    def card() -> None:
        p().locator(".arm-jrow", has_text="Отработана").first.locator(".c-type").click()
        p().wait_for_url(re.compile(r"/arm/112/[0-9a-f-]{36}"))
        p().wait_for_load_state("networkidle")
        time.sleep(1.5)
        sh.shot("t23_card_check")

    sh.step("t23_card_check", card)


def student_part(sh: Shooter, d: dict[str, Any]) -> None:
    p = lambda: sh.p  # noqa: E731
    sh.login("op2", "3", shot="s01_login", tours=True)
    sh.step("s02_tour", lambda: (p().get_by_text("Шаг 1 из").wait_for(), sh.shot("s02_tour")))
    sh.p.evaluate(ONBOARDING, "dismiss")
    sh.go("/student", 1.5)
    sh.shot("s03_home")
    sh.step("s04_history", lambda: (sh.scroll_to("[data-tour='history']"), sh.shot("s04_history")))

    sh.go("/arm/112/journal", 2)
    sh.shot("s05_journal")
    teacher: httpx.Client = d["teacher"]
    call: dict[str, Any] = {}
    sh.p.on(
        "response", lambda r: call.update(r.json()) if r.url.endswith("/training/calls/incoming") and r.ok else None
    )

    def ring() -> None:
        btn = p().get_by_role("button", name=re.compile("ответить", re.I))
        if not btn.count():
            p().get_by_text("учебный вызов").first.click()
        btn.first.wait_for(timeout=45_000)
        time.sleep(0.8)
        sh.shot("s06_ring")
        btn.first.click()
        p().wait_for_url(re.compile(r"/arm/112/[0-9a-f-]{36}"), timeout=15_000)
        p().wait_for_load_state("networkidle")
        time.sleep(2.5)
        composer = p().get_by_placeholder("Что вы говорите в трубку…")
        for q in ("Что случилось?", "Назовите точный адрес", "Есть пострадавшие?"):
            composer.fill(q)
            composer.press("Enter")
            time.sleep(3.5)
        sh.shot("s07_call")
        p().locator(".call-panel__end").click()  # окно разговора закрывает опросную карту
        time.sleep(1)
        if p().locator(".call-panel__close").count():
            p().locator(".call-panel__close").click()
            time.sleep(0.5)

    sh.step("s07_call", ring)
    ref = teacher.get(f"/training/scenarios/{call['scenario_id']}").json()["reference_card"] if call else {}

    def address() -> None:
        a = ref["address"]
        house = a["house"] + (f" к{a['building']}" if a.get("building") else "")
        line = p().locator("#address-line")
        line.click()
        line.press_sequentially(f"{a['street']} {a['house']}", delay=40)
        opts = p().locator("[role=listbox]:visible [role=option]")
        opts.first.wait_for(timeout=8000)
        time.sleep(0.8)
        sh.shot("s08_address")
        exact = opts.filter(has_text=f", {house} ")
        (exact.first if exact.count() else opts.first).click()
        time.sleep(1.5)
        if p().get_by_label("Закрыть карту (Esc)").count():
            sh.shot("s09_map")
            p().keyboard.press("Escape")
            time.sleep(0.6)

    sh.step("s08_address", address)

    def what() -> None:
        p().locator("#applicant-name").fill(ref["applicant"]["name"])
        p().get_by_label("Статус заявителя").select_option(ref["applicant"]["status"])
        box = p().locator("#what-happened")
        box.click()
        types = {t["code"]: t for t in teacher.get("/dictionaries/card-types").json()}
        code = ref["card_types"][0]
        box.press_sequentially(str(types.get(code, {}).get("title") or code), delay=40)
        p().locator("#what-happened-list [role=option]").first.wait_for(timeout=8000)
        time.sleep(0.6)
        p().locator("#what-happened-list [role=option]").first.click()
        time.sleep(1.2)
        sh.shot("s10_what")
        p().get_by_role("button", name="сохранить", exact=True).click()  # опросная карта не пройдена — подсказка
        time.sleep(1)
        sh.shot("s12_required")
        p().locator(".arm112-banner").click()  # подсказка закрывается щелчком; Esc закрыл бы саму карточку
        time.sleep(0.5)

    sh.step("s10_what", what)

    def fill_and_save() -> None:
        for answers in (ref.get("questionnaire") or {}).values():
            for level in sorted(answers):
                p().get_by_role("button", name=answers[level], exact=True).first.evaluate("el => el.click()")
                time.sleep(0.6)
        if ref["victims"].get("has"):
            p().locator("#victims").click()
        p().locator("#description").fill(
            " ".join(ref["description_keywords"][:4]) + ", заявитель сообщает о происшествии"
        )
        time.sleep(1)
        sh.shot("s11_filled")
        p().get_by_role("button", name="сохранить", exact=True).click()
        time.sleep(1)
        sh.shot("s13_confirm")
        p().get_by_role("button", name="оповестить и сохранить карточку").click(timeout=5000)
        time.sleep(3.5)
        sh.shot("s14_saved")

    sh.step("s11_save", fill_and_save)

    sh.login("dds1", "7")
    sh.go("/arm/dds", 1.5)
    sh.shot("s15_dds_select")
    sh.go("/arm/dds/S101", 2)
    sh.shot("s16_dds_journal")

    def dds_card() -> None:
        p().locator(".arm-jrow").first.dblclick()
        p().wait_for_url(re.compile(r"/arm/dds/S101/[0-9a-f-]{36}"))
        p().wait_for_load_state("networkidle")
        time.sleep(1.5)
        sh.shot("s17_dds_card")
        p().locator("button:visible", has_text="изменить статус").first.click()
        time.sleep(1)  # редактор пересоздаётся сразу после открытия — ввод до этого теряется
        editor = p().get_by_role("dialog", name="Изменение статуса службы")
        editor.get_by_label("Статус", exact=True).select_option("accepted")
        editor.get_by_placeholder("Номер наряда").fill("12")
        editor.get_by_placeholder("Комментарий").fill("Выслан наряд ПСЧ-12")
        time.sleep(0.6)
        sh.shot("s18_dds_status")
        editor.get_by_label("Сохранить статус").click()
        time.sleep(1.5)
        p().get_by_role("button", name="Старший группы").first.click()
        box = p().get_by_placeholder("Что вы говорите в трубку…")
        box.wait_for(timeout=8000)
        time.sleep(1.2)
        box.fill("Доложите обстановку")
        box.press("Enter")
        time.sleep(4)
        sh.shot("s19_dds_phone")

    sh.step("s17_dds", dds_card)

    sh.login("op2", "3")
    sh.go("/student/progress", 1.5)
    sh.shot("s20_progress")
    sh.go(f"/student/sessions/{d['s6']}", 1.5)
    sh.shot("s21_session_result")
    sh.go("/student/reference", 1.5)
    sh.shot("s22_reference")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--web", default="http://localhost:5174")
    ap.add_argument("--only", choices=["teacher", "student"])
    args = ap.parse_args()
    password = os.environ["AISKRA_DEMO_PASSWORD"]
    IMG.mkdir(parents=True, exist_ok=True)
    data = prepare(args.web, password)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome")
        sh = Shooter(browser, args.web, password)
        if args.only != "student":
            teacher_part(sh, data)
        if args.only != "teacher":
            student_part(sh, data)
        browser.close()
    print("не снято:", sh.failed or "—")


if __name__ == "__main__":
    main()
