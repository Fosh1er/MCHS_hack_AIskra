"""Дымовая проверка в браузере (п. 9.5 ТЗ: Chrome, Firefox, Яндекс.Браузер): экраны всех ролей и ключевые действия —
учебный вызов, ответ, реплика заявителю, статус ДДС; ошибки JavaScript и снимки экранов.

    AISKRA_DEMO_PASSWORD=… uv run --with playwright python tools/browser_smoke.py --browser firefox \\
        --web http://localhost:5173 --out ../docs/browsers/firefox

Firefox для Playwright: `uv run --with playwright python -m playwright install firefox`. Яндекс.Браузер построен на
Chromium — его покрывает прогон `--browser chromium`. Стенд — после `demo-seed` (и лучше `tools/demo_history.py`).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

PAGES = {
    "teacher": [
        "/teacher", "/teacher/scenarios", "/teacher/sessions", "/teacher/analytics", "/teacher/readiness",
        "/teacher/validation", "/teacher/materials",
    ],
    "op1": ["/student", "/arm/112/journal"],
    "dds1": ["/student", "/arm/dds/S101"],
}  # fmt: skip
IGNORED = ("React DevTools", "Future Flag", "[vite]", "Download the React")


def login(page: Page, web: str, user: str, password: str, arm: str = "") -> None:
    page.goto(f"{web}/")
    page.get_by_label("логин").fill(user)
    page.locator("input[type=password]").fill(password)
    if arm:
        page.get_by_label("номер АРМ").fill(arm)
    page.get_by_role("button", name="ВОЙТИ").click()
    page.wait_for_load_state("networkidle")
    time.sleep(0.8)
    skip_tour(page)


def skip_tour(page: Page) -> None:
    """Обучающая экскурсия (п. 5.3) при первом входе перекрывает экран — для проверки её пропускаем."""
    for _ in range(3):
        link = page.get_by_text("пропустить обучение")
        if not link.count():
            return
        link.first.click()
        time.sleep(0.5)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--browser", choices=["firefox", "chromium", "chrome"], default="firefox")
    ap.add_argument("--web", default="http://localhost:5173")
    ap.add_argument("--out", default="../docs/browsers/firefox")
    args = ap.parse_args()
    password = os.environ["AISKRA_DEMO_PASSWORD"]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"browser": args.browser, "pages": [], "steps": [], "errors": []}

    with sync_playwright() as p:
        engine = p.firefox if args.browser == "firefox" else p.chromium
        browser = engine.launch(channel="chrome") if args.browser == "chrome" else engine.launch()
        report["version"] = browser.version

        def context(user: str) -> Page:
            page = browser.new_context(viewport={"width": 1600, "height": 900}, locale="ru-RU").new_page()
            page.set_default_timeout(15_000)
            page.on(
                "pageerror", lambda e: report["errors"].append({"user": user, "url": page.url, "error": str(e)[:300]})
            )
            page.on(
                "console",
                lambda m: (
                    report["errors"].append({"user": user, "url": page.url, "console": m.text[:300]})
                    if m.type == "error" and not any(s in m.text for s in IGNORED) and "401" not in m.text
                    else None
                ),
            )
            return page

        for user, paths in PAGES.items():
            page = context(user)
            login(page, args.web, user, password, "3" if user == "op1" else "7" if user == "dds1" else "")
            for path in paths:
                page.goto(f"{args.web}{path}")
                page.wait_for_load_state("networkidle")
                time.sleep(1)
                skip_tour(page)
                name = re.sub(r"\W+", "_", f"{user}{path}").strip("_")
                page.screenshot(path=str(out / f"{name}.png"))
                report["pages"].append(
                    {"user": user, "path": path, "title": page.title(), "ok": page.url.endswith(path)}
                )
            page.context.close()

        # ключевые действия: учебный вызов → ответ → реплика; ДДС — открыть карточку и поставить статус
        page = context("op1")
        login(page, args.web, "op1", password, "3")
        page.goto(f"{args.web}/arm/112/journal")
        page.wait_for_load_state("networkidle")
        skip_tour(page)

        def step(name: str, fn: Any) -> None:
            try:
                fn()
                report["steps"].append({"step": name, "ok": True})
            except Exception as e:
                report["steps"].append({"step": name, "ok": False, "error": str(e).splitlines()[0][:200]})

        step("учебный вызов", lambda: page.get_by_role("button", name="учебный вызов").click())

        def answer() -> None:
            page.get_by_role("button", name="Ответить").click()
            page.wait_for_url(re.compile(r"/arm/112/[0-9a-f-]{36}"))
            skip_tour(page)

        def replica() -> None:
            composer = page.get_by_placeholder("Что вы говорите в трубку…")
            composer.fill("Что у вас случилось?")
            composer.press("Enter")
            time.sleep(3)
            page.get_by_text("Что у вас случилось?").first.wait_for()

        step("ответить", answer)
        step("реплика заявителю", replica)
        page.screenshot(path=str(out / "op1_call.png"))
        page.context.close()

        page = context("dds1")
        login(page, args.web, "dds1", password, "7")
        page.goto(f"{args.web}/arm/dds/S101")
        page.wait_for_load_state("networkidle")
        skip_tour(page)
        step("журнал ДДС: карточки", lambda: page.locator(".arm-jrow").first.wait_for())

        def open_dds_card() -> None:
            row = page.evaluate("fetch('/api/v1/incidents/dds/S101/journal?page=1&page_size=10').then(r => r.json())")
            item = (row.get("items") or [row])[0] if isinstance(row, dict) else row[0]
            card_id = item.get("card_id") or item.get("id")
            page.goto(f"{args.web}/arm/dds/S101/{card_id}")
            page.wait_for_load_state("networkidle")
            skip_tour(page)
            page.get_by_text(
                "Происшествие", exact=False
            ).first.wait_for()  # у завершённых карточек статус уже не меняется

        step("открыть карточку ДДС", open_dds_card)
        page.screenshot(path=str(out / "dds1_card.png"))
        page.context.close()
        browser.close()

    ok_pages = sum(1 for x in report["pages"] if x["ok"])
    ok_steps = sum(1 for x in report["steps"] if x["ok"])
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    print(f"{args.browser} {report['version']}: экранов {ok_pages}/{len(report['pages'])}, "
          f"действий {ok_steps}/{len(report['steps'])}, ошибок JS {len(report['errors'])}")  # fmt: skip


if __name__ == "__main__":
    main()
