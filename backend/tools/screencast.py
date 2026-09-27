"""Скринкаст демо (п. 7.4): сквозной сценарий из плана — оператор 112 принимает вводную → карточка → службы → ДДС
получает → принимает → звонок старшему группы → статусы → отчёт преподавателя. Запись Playwright (Chrome с машины),
одна вкладка, роли сменяются входом; подписи шагов поверх экрана. Результат — webm (и mp4, если есть imageio-ffmpeg).

    AISKRA_DEMO_PASSWORD=… uv run --with playwright --with httpx --with imageio-ffmpeg \\
        python tools/screencast.py --web http://localhost:5173 --out ../docs/demo/screencast

Стенд — после `demo-seed` и `tools/demo_history.py`; занятие для показа создаётся здесь же.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
from playwright.sync_api import sync_playwright

CAPTION_JS = """
(() => {
  const text = sessionStorage.getItem('aiskra-caption') || '';
  let el = document.getElementById('aiskra-caption');
  if (!el) {
    el = document.createElement('div');
    el.id = 'aiskra-caption';
    el.style.cssText = 'position:fixed;left:50%;bottom:18px;transform:translateX(-50%);z-index:99999;' +
      'background:rgba(16,24,40,.88);color:#fff;font:600 20px/1.3 Roboto,Arial,sans-serif;padding:10px 18px;' +
      'border-radius:6px;box-shadow:0 4px 18px rgba(0,0,0,.35);pointer-events:none;max-width:80%;text-align:center';
    document.documentElement.appendChild(el);
  }
  el.textContent = text;
  el.style.display = text ? 'block' : 'none';
})();
"""


class Show:
    """Одна роль — свой контекст браузера (свои cookie) и свой сегмент видео; сегменты склеиваются в один ролик."""

    def __init__(self, browser: Any, web: str, password: str, out: Path, on_page: Any) -> None:
        self.browser, self.web, self.password, self.out, self.on_page = browser, web, password, out, on_page
        self.ctx: Any = None
        self.page: Any = None
        self.segments: list[Path] = []
        self.caption_text = ""

    def close(self) -> None:
        if self.ctx is not None:
            video = self.page.video
            self.ctx.close()
            if video:
                self.segments.append(Path(video.path()))

    def caption(self, text: str, hold: float = 2.5) -> None:
        self.caption_text = text
        self.page.evaluate("t => sessionStorage.setItem('aiskra-caption', t)", text)
        self.page.evaluate(CAPTION_JS)
        time.sleep(hold)

    def login(self, user: str, arm: str = "") -> None:
        self.close()
        self.ctx = self.browser.new_context(
            viewport={"width": 1600, "height": 900}, locale="ru-RU",
            record_video_dir=str(self.out / "raw"), record_video_size={"width": 1600, "height": 900},
        )  # fmt: skip
        self.page = self.ctx.new_page()
        self.page.set_default_timeout(8000)
        self.page.on("dialog", lambda d: d.accept())
        self.on_page(self.page)
        SHOTS.update(page=self.page)
        self.page.goto(f"{self.web}/")
        self.page.wait_for_load_state("networkidle")
        self.page.get_by_label("логин").fill(user)
        self.page.locator("input[type=password]").fill(self.password)
        if arm:
            self.page.get_by_label("номер АРМ").fill(arm)
        time.sleep(0.6)
        self.page.get_by_role("button", name="ВОЙТИ").click()
        self.page.wait_for_load_state("networkidle")
        time.sleep(1)

    def go(self, path: str, wait: float = 2.0) -> None:
        self.page.goto(f"{self.web}{path}")
        self.page.wait_for_load_state("networkidle")
        self.page.evaluate(CAPTION_JS)
        time.sleep(wait)

    def type(self, selector: str, text: str) -> None:
        loc = self.page.locator(selector).first
        loc.click()
        loc.press_sequentially(text, delay=45)


class PageProxy:
    """`page` сценария — текущая вкладка текущей роли."""

    def __init__(self, show: Show) -> None:
        self._show = show

    def __getattr__(self, name: str) -> Any:
        return getattr(self._show.page, name)


def api(base: str, user: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=f"{base}/api/v1", timeout=30)
    c.post("/auth/login", json={"login": user, "password": password}).raise_for_status()
    return c


FAILED: list[str] = []
SHOTS: dict[str, Any] = {}


def try_step(name: str, fn: Any) -> None:
    """Шаг ролика: при сбое ролик продолжается, шаг и скриншот — в журнал."""
    try:
        fn()
    except Exception as e:
        FAILED.append(name)
        print(f"шаг «{name}» пропущен: {type(e).__name__}: {str(e).splitlines()[0][:160]}", flush=True)
        page = SHOTS.get("page")
        if page is not None:
            page.screenshot(path=str(SHOTS["dir"] / f"fail_{len(FAILED):02d}.png"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--web", default="http://localhost:5173")
    ap.add_argument("--api", default="", help="адрес API, если не через прокси клиента")
    ap.add_argument("--out", default="../docs/demo/screencast")
    args = ap.parse_args()
    password = os.environ["AISKRA_DEMO_PASSWORD"]
    base = args.api or args.web
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    teacher = api(base, "teacher", password)
    for s in teacher.get("/training/sessions", params={"limit": 50}).json()["items"]:
        if s["status"] == "running":
            teacher.post(f"/training/sessions/{s['id']}/finish")
    people = {s["login"]: s["id"] for s in teacher.get("/training/students").json()}
    session_id = teacher.post(
        "/training/sessions",
        json={
            "title": "Смена 1: пожары в жилом секторе",
            "mode": "mixed",
            "card_source": "trainee",
            "groups": [1],
            "participants": [
                {"student_id": people["op1"], "role": "112"},
                {"student_id": people["op2"], "role": "112"},
                {"student_id": people["dds1"], "role": "dds", "dds_service_code": "S101"},
                {"student_id": people["dds2"], "role": "dds", "dds_service_code": "S103"},
            ],
            "settings": {"difficulty": 2, "call_interval_s": 8, "feed_interval_s": 60},
        },
    ).json()["id"]

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        scenario: dict[str, Any] = {}

        def on_page(pg: Any) -> None:
            pg.on(
                "response",
                lambda r: scenario.update(r.json()) if r.url.endswith("/training/calls/incoming") and r.ok else None,
            )

        SHOTS.update(dir=out)
        show = Show(browser, args.web, password, out, on_page)
        page = PageProxy(show)

        # 1. преподаватель
        show.login("teacher")
        show.caption("АИскра — ИИ-тренажёр операторов 112 и диспетчеров ДДС", 4.8)
        show.go("/teacher/scenarios")
        show.caption("Банк сценариев: ИИ генерирует легенду заявителя вместе с эталоном карточки и действий ДДС", 6.4)
        show.go(f"/teacher/sessions/{session_id}")
        show.caption("Преподаватель запускает смешанное занятие: операторы 112 и диспетчеры ДДС", 3.2)
        page.get_by_role("button", name="начать занятие").click()
        show.caption("Занятие идёт: мониторинг по каждому обучающемуся", 4.8)

        # 2. оператор 112
        show.login("op1", "3")
        show.caption("Оператор 112: журнал, поток учебных вызовов включён занятием", 3.2)
        page.get_by_role("button", name="Ответить").click(timeout=45_000)
        page.wait_for_url(re.compile(r"/arm/112/[0-9a-f-]{36}"), timeout=15_000)
        card_id = page.url.split("/arm/112/")[1].split("?")[0]
        show.caption("Входящий вызов → карточка 112 открыта, ИИ-заявитель на линии", 4.8)
        ref = teacher.get(f"/training/scenarios/{scenario['scenario_id']}").json()["reference_card"]
        composer = page.get_by_placeholder("Что вы говорите в трубку…")
        for q in ("Что случилось?", "Назовите точный адрес", "Есть пострадавшие?", "Как вас зовут?"):
            try_step(q, lambda q=q: (composer.fill(q), composer.press("Enter"), time.sleep(4)))
        show.caption("Оператор опрашивает заявителя — ИИ отвечает только сведениями легенды", 3.2)
        try_step("завершить разговор", lambda: page.get_by_role("button", name="завершить").first.click())
        time.sleep(1)

        a = ref["address"]

        def address() -> None:
            house = a["house"] + (f" к{a['building']}" if a.get("building") else "")
            show.type("#address-line", f"{a['street']} {a['house']}")
            opts = page.locator("[role=listbox]:visible [role=option]")
            opts.first.wait_for(timeout=8000)
            time.sleep(0.8)
            exact = opts.filter(has_text=f", {house} ")
            (exact.first if exact.count() else opts.first).click()
            time.sleep(1.5)
            if page.get_by_label("Закрыть карту (Esc)").count():  # карта открывается при выборе адреса
                page.keyboard.press("Escape")

        try_step("адрес", address)
        try_step("заявитель", lambda: show.type("#applicant-name", ref["applicant"]["name"]))
        try_step(
            "статус заявителя",
            lambda: page.get_by_label("Статус заявителя").select_option(ref["applicant"]["status"]),
        )

        def what() -> None:
            show.type("#what-happened", ref["card_types"][0])  # «что случилось?» — тип карточки классификатора
            opt = page.locator("#what-happened-list [role=option]").first
            opt.wait_for(timeout=8000)
            time.sleep(0.8)
            opt.click()
            time.sleep(1)

        try_step("тип происшествия", what)
        show.caption("Тип по классификатору заказчика, опросная карта — службы подбираются сами", 3)
        for answers in (ref.get("questionnaire") or {}).values():
            for level in sorted(answers):
                label = answers[level]
                try_step(
                    label,
                    lambda label=label: (
                        page.get_by_role("button", name=label, exact=True).first.evaluate("el => el.click()"),
                        time.sleep(0.7),
                    ),
                )
        if ref["victims"].get("has"):
            try_step("пострадавшие", lambda: page.locator("#victims").click())
        try_step(
            "описание",
            lambda: show.type(
                "#description", " ".join(ref["description_keywords"][:4]) + ", заявитель сообщает о происшествии"
            ),
        )
        show.caption("Службы на оранжевой панели — по матрице классификатора, адресу и признакам", 4.8)

        def save() -> None:
            page.get_by_role("button", name="сохранить", exact=True).click()
            page.get_by_role("button", name="оповестить и сохранить карточку").click(timeout=5000)

        try_step("сохранить", save)
        show.caption("Карточка сохранена — автооценка по эталону: балл и замечания", 8)

        # 3. диспетчер ДДС
        show.login("dds1", "7")
        show.go("/arm/dds/S101", 3)
        show.caption("АРМ ДДС «Служба 101»: карточка оператора пришла в очередь, идёт таймер решения", 4.8)

        show.go(f"/arm/dds/S101/{card_id}", 2)

        def status(value: str, comment: str, order: str | None = None) -> None:
            page.locator("button:visible", has_text="изменить статус").first.click()
            editor = page.get_by_role("dialog", name="Изменение статуса службы")
            editor.get_by_label("Статус", exact=True).select_option(value)
            if order:
                editor.get_by_placeholder("Номер наряда").fill(order)
            editor.get_by_placeholder("Комментарий").press_sequentially(comment, delay=35)
            time.sleep(0.5)
            editor.get_by_label("Сохранить статус").click()
            time.sleep(1.5)

        show.caption("Диспетчер принимает карточку: номер наряда и комментарий", 1)
        try_step("принята", lambda: status("accepted", "Выслан наряд ПСЧ-12", "12"))
        try_step("выехала", lambda: status("response_started", "Наряд выехал"))

        def call_brigade() -> None:
            page.get_by_role("button", name="Старший группы").first.click()
            box = page.get_by_placeholder("Что вы говорите в трубку…")
            box.wait_for(timeout=8000)
            time.sleep(1.5)
            box.fill("Доложите обстановку")
            box.press("Enter")
            time.sleep(4)

        show.caption("IP-телефон: звонок старшему группы — ИИ докладывает по текущему статусу", 1)
        try_step("звонок старшему", call_brigade)
        try_step("завершить звонок", lambda: page.get_by_role("button", name="завершить").first.click())
        for value, text in (
            ("arrived", "Прибыли на место"),
            ("works_in_progress", "Работы начаты"),
            ("works_completed", "Работы завершены, пострадавший передан СМП"),
        ):
            try_step(value, lambda value=value, text=text: status(value, text))
        show.caption("Статусы службы доведены до «Работы завершены»", 4.8)

        # 4. преподаватель: результаты
        show.login("teacher")
        show.go(f"/teacher/sessions/{session_id}", 1)
        show.caption("Мониторинг: карточки, таймеры против норматива, баллы", 6.4)
        try_step("завершить", lambda: page.get_by_role("button", name="завершить").click())
        show.go(f"/teacher/sessions/{session_id}/report", 1)
        try_step("оценить", lambda: (page.get_by_role("button", name="оценить все карточки").click(), time.sleep(3)))
        show.caption("Отчёт: баллы, замечания по критериям, время против норматива, экспертная правка", 6.4)
        page.mouse.wheel(0, 700)
        show.caption("Тепловая карта ошибок и время заполнения карточек", 6.4)
        show.go(f"/teacher/sessions/{session_id}/debrief", 1)
        show.caption("Разбор занятия: характерные недостатки группы, превышения норматива, лучшие", 6)
        show.go("/teacher/analytics", 1)
        show.caption("Аналитика: норматив / факт по ПП РФ № 1931 за две недели занятий", 6.4)
        profile = next(
            (r["key"] for r in teacher.get("/assessment/analytics/norms", params={"days": 0}).json()["by_student"]
             if r["role"] == "112" and r["title"].startswith("Волкова")),
            people["op2"],
        )  # fmt: skip
        show.go(f"/teacher/students/{profile}", 1)
        show.caption("Профиль обучающегося: критерии против группы, типичные ошибки, индивидуальное задание", 6)
        page.mouse.wheel(0, 900)
        show.caption("Группы классификатора: что отработано и что ещё не встречалось", 4)
        show.go("/teacher/readiness", 1)
        show.caption("Готовность к допуску по шкале Программы подготовки ЕДДС — и протокол", 6.4)
        show.go("/teacher/validation", 2)
        show.caption("Достоверность автооценки: 602 проверки на 30 сценариях", 6.4)
        show.caption("", 0.5)
        show.close()
        browser.close()

    segments = [seg for seg in show.segments if seg.exists()]
    try:
        import imageio_ffmpeg  # type: ignore[import-not-found]
    except ImportError:
        print("склейка не выполнена: нет imageio-ffmpeg; сегменты —", out / "raw")
        return
    mp4 = out / "АИскра_скринкаст.mp4"
    inputs = [arg for seg in segments for arg in ("-i", str(seg))]
    joined = "".join(f"[{i}:v]" for i in range(len(segments))) + f"concat=n={len(segments)}:v=1:a=0[v]"
    subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", *inputs, "-filter_complex", joined, "-map", "[v]",
         "-c:v", "libx264", "-preset", "slow", "-crf", "26", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
         str(mp4)],
        check=True,
    )  # fmt: skip
    shutil.rmtree(out / "raw", ignore_errors=True)
    print("mp4:", mp4, f"(сегментов: {len(segments)})")


if __name__ == "__main__":
    main()
