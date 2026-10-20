"""E2E-стенд (F6.5): временная SQLite-база, модель-заглушка, backend (uvicorn) и собранный фронтенд (vite preview).

Стенд поднимается один раз на сессию pytest, каждый тест работает в своём контексте браузера. Запуск — `make e2e`
(firefox: `make e2e E2E_BROWSER=firefox`). Обычный `make be-test` эти тесты не собирает (`testpaths` в pyproject).
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest

pytest.importorskip("playwright", reason="e2e: нужен playwright — запускайте через `make e2e`")

from playwright.sync_api import Browser, BrowserContext, ConsoleMessage, Page, Playwright, Response, sync_playwright

from tests.e2e.mock_llm import MockLLM, tone_wav

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
FRONTEND = REPO / "frontend"
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
TIMEOUT_MS = 15_000

# Переменные разработчика не должны попасть в стенд: ключи, адреса моделей и настройки — только свои.
_FOREIGN = ("AISKRA_", "DEMO_", "TTS_", "STT_", "OPENROUTER", "OPENAI")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def wait_http(url: str, timeout: float = 60.0, proc: subprocess.Popen[bytes] | None = None) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            raise RuntimeError(f"процесс завершился с кодом {proc.returncode}, не дождавшись {url}")
        try:
            if httpx.get(url, timeout=2).status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    raise TimeoutError(f"нет ответа от {url} за {timeout:.0f} с")


def clean_env(extra: dict[str, str]) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(_FOREIGN)}
    env.update(extra)
    return env


@dataclass
class Proc:
    """Процесс стенда с журналом в файл; перезапускается с теми же параметрами."""

    name: str
    cmd: list[str]
    cwd: Path
    env: dict[str, str]
    health: str
    log: Path
    proc: subprocess.Popen[bytes] | None = None

    def start(self, timeout: float = 90.0) -> None:
        out = self.log.open("ab")
        out.write(f"\n=== {self.name}: старт {time.strftime('%H:%M:%S')} ===\n".encode())
        out.flush()
        self.proc = subprocess.Popen(self.cmd, cwd=self.cwd, env=self.env, stdout=out, stderr=subprocess.STDOUT)
        try:
            wait_http(self.health, timeout, self.proc)
        except Exception as e:
            self.stop()
            tail = self.log.read_text("utf-8", errors="replace")[-3000:]
            raise RuntimeError(f"{self.name} не запустился: {e}\n{tail}") from e

    def stop(self) -> None:
        if self.proc is None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(5)
        self.proc = None

    def restart(self) -> None:
        self.stop()
        self.start()


@dataclass
class Stand:
    web: str
    api: str
    password: str
    admin_password: str
    mock: MockLLM
    backend: Proc
    frontend: Proc
    home: Path
    _clients: dict[str, httpx.Client] = field(default_factory=dict)

    def client(self, login: str) -> httpx.Client:
        """API от имени пользователя (подготовка данных и проверки, не замена интерфейса). Сессия кешируется."""
        c = self._clients.get(login)
        if c is None or c.get("/auth/me").status_code != 200:
            c = httpx.Client(base_url=f"{self.api}/api/v1", timeout=30)
            pw = self.admin_password if login == "admin" else self.password
            r = c.post("/auth/login", json={"login": login, "password": pw})
            assert r.status_code == 200, f"вход {login}: {r.status_code} {r.text[:200]}"
            c.post("/auth/onboarding", json={"action": "dismiss"})  # подсказки (п. 5.3) перекрыли бы экран
            self._clients[login] = c
        return c


def _run(cmd: list[str], env: dict[str, str], cwd: Path, log: Path) -> None:
    with log.open("ab") as out:
        out.write(f"\n$ {' '.join(cmd)}\n".encode())
        out.flush()
        r = subprocess.run(cmd, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT, timeout=600)
    if r.returncode:
        raise RuntimeError(
            f"{' '.join(cmd[2:5])}: код {r.returncode}\n{log.read_text('utf-8', errors='replace')[-3000:]}"
        )


@pytest.fixture(scope="session")
def stand(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stand]:
    home = tmp_path_factory.mktemp("stand")
    log = home / "stand.log"
    password = "e2e-" + secrets.token_urlsafe(12)
    admin_password = "e2e-adm-" + secrets.token_urlsafe(12)
    common = {
        "AISKRA_DATABASE_URL": f"sqlite+aiosqlite:///{home / 'aiskra.db'}",
        "AISKRA_BACKUP_DIR": str(home / "backups"),
        "AISKRA_MATERIALS_DIR": str(home / "materials"),
        "AISKRA_SCHEDULER_ENABLED": "false",
        "AISKRA_AI_ALLOW_EXTERNAL": "false",  # заглушка на 127.0.0.1; внешние адреса запрещены конфигом
        "AISKRA_BOOTSTRAP_ADMIN_PASSWORD": admin_password,
        "AISKRA_DEMO_PASSWORD": password,
        "PYTHONUNBUFFERED": "1",
    }
    py = sys.executable
    # 1. база: миграции, справочники, адреса, администратор, демо-стенд (генерация сценариев — офлайн, быстро)
    seed_env = clean_env({**common, "AISKRA_AI_CONFIG_PATH": str(REPO / "config" / "ai.yaml")})
    _run([py, "-m", "alembic", "-c", str(BACKEND / "alembic.ini"), "upgrade", "head"], seed_env, BACKEND, log)
    for args in (
        ["import-dictionaries"],
        ["import-addresses"],
        ["ensure-admin"],
        ["demo-seed", "--scenarios", "12", "--load-users", "3"],
    ):
        _run([py, "-m", "aiskra.cli", *args], seed_env, home, log)

    # 2. модель-заглушка (LLM, TTS, STT) на свободном порту
    mock = MockLLM(free_port()).start()

    # 3. backend на конфиге демо-стенда, все модели и речь — на заглушку
    api_port, web_port = free_port(), free_port()
    backend_env = clean_env({
        **common,
        "AISKRA_APP_ENV": "demo",
        "AISKRA_AI_CONFIG_PATH": str(REPO / "config" / "ai.openrouter.yaml"),
        "DEMO_LLM_URL": mock.url, "DEMO_LLM_MODEL": "e2e-mock", "DEMO_SMALL_MODEL": "e2e-mock-small",
        "TTS_KIND": "openai_compatible", "TTS_URL": mock.url, "TTS_FORMAT": "wav", "TTS_MODEL": "e2e-tts",
        "STT_KIND": "openai_compatible", "STT_URL": mock.url,
    })  # fmt: skip
    backend = Proc(
        "backend",
        [py, "-m", "uvicorn", "aiskra.main:app", "--host", "127.0.0.1", "--port", str(api_port)],
        home, backend_env, f"http://127.0.0.1:{api_port}/health", home / "backend.log",
    )  # fmt: skip

    # 4. фронтенд: собранный dist за vite preview с прокси /api → backend (как nginx на стенде)
    if not (FRONTEND / "dist" / "index.html").exists() or os.environ.get("E2E_BUILD") == "1":
        _run(["npm", "run", "build"], clean_env({}), REPO, log)
    vite = next(p for p in (FRONTEND / "node_modules/.bin/vite", REPO / "node_modules/.bin/vite") if p.exists())
    frontend = Proc(
        "frontend",
        [str(vite), "preview", "--host", "127.0.0.1", "--port", str(web_port), "--strictPort"],
        FRONTEND,
        clean_env({"AISKRA_API": f"http://127.0.0.1:{api_port}", "AISKRA_DEV_HTTP": "1"}),
        f"http://127.0.0.1:{web_port}/",
        home / "frontend.log",
    )
    s = Stand(
        web=f"http://127.0.0.1:{web_port}",
        api=f"http://127.0.0.1:{api_port}",
        password=password,
        admin_password=admin_password,
        mock=mock,
        backend=backend,
        frontend=frontend,
        home=home,
    )
    try:
        backend.start()
        frontend.start()
        # роль оператора 112 по умолчанию скрыта (рекомендации экспертов) — набор проверяет обе роли, включаем её
        r = s.client("admin").put("/system/settings/services", json={"values": {"role_112": 1}})
        assert r.status_code == 200, r.text
        for login in ("teacher", "op1", "op2", "dds1", "dds2", "load001", "load002", "load003"):
            s.client(login)
        yield s
    finally:
        for c in s._clients.values():
            c.close()
        frontend.stop()
        backend.stop()
        mock.stop()
        if os.environ.get("E2E_KEEP_LOGS"):
            print(f"\nжурналы стенда: {home}")


# --------------------------------------------------------------------------------------------------- браузер


def pytest_sessionstart(session: pytest.Session) -> None:
    shutil.rmtree(ARTIFACTS, ignore_errors=True)  # артефакты — только прогона, который их оставил


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--e2e-browser", default=os.environ.get("E2E_BROWSER", "chromium"), choices=["chromium", "firefox"]
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Iterator[None]:
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


@pytest.fixture(scope="session")
def browser_name(pytestconfig: pytest.Config) -> str:
    return str(pytestconfig.getoption("--e2e-browser"))


@pytest.fixture(scope="session")
def playwright() -> Iterator[Playwright]:
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright: Playwright, browser_name: str, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Browser]:
    if browser_name == "firefox":
        b = playwright.firefox.launch(
            firefox_user_prefs={
                "media.navigator.streams.fake": True,  # микрофон — синтетический сигнал, без запроса разрешения
                "media.navigator.permission.disabled": True,
                "media.autoplay.default": 0,
            }
        )
    else:
        # микрофон — файл: тишина (калибровка VAD), «фраза» 1,5 с, тишина (конец фразы); файл играется по кругу
        voice = tmp_path_factory.mktemp("mic") / "phrase.wav"
        voice.write_bytes(tone_wav(1.5, 16_000, silence_before=1.2, silence_after=2.5))
        b = playwright.chromium.launch(
            args=[
                "--use-fake-device-for-media-stream",
                "--use-fake-ui-for-media-stream",
                f"--use-file-for-fake-audio-capture={voice}",
                "--autoplay-policy=no-user-gesture-required",
            ]
        )
    yield b
    b.close()


# Сообщения консоли, которые не ошибки приложения: загрузка ресурса с кодом ответа (её видно по сети — ниже),
# служебные сообщения инструментов.
IGNORED_CONSOLE = ("Failed to load resource", "React DevTools", "Download the React", "[vite]")


@dataclass
class BrowserErrors:
    """Ошибки JavaScript и ответы API 5xx за тест. Ожидаемые отказы тест разрешает `allow(шаблон)`."""

    items: list[str] = field(default_factory=list)
    allowed: list[re.Pattern[str]] = field(default_factory=list)
    log: list[str] = field(default_factory=list)  # вся консоль и ошибки — в артефакты при падении

    def allow(self, pattern: str) -> None:
        self.allowed.append(re.compile(pattern))

    def add(self, text: str) -> None:
        self.log.append(text)
        if not any(p.search(text) for p in self.allowed):
            self.items.append(text)


@dataclass
class Session:
    """Контексты браузера одного теста: по контексту на роль (свои cookie)."""

    browser: Browser
    stand: Stand
    errors: BrowserErrors
    contexts: list[BrowserContext] = field(default_factory=list)
    pages: list[Page] = field(default_factory=list)

    def new_page(self, login: str | None = None, *, voice: bool = False) -> Page:
        ctx = self.browser.new_context(viewport={"width": 1600, "height": 900}, locale="ru-RU")
        if login:
            c = self.stand.client(login)
            ctx.add_cookies([
                {"name": k, "value": v, "url": self.stand.web} for k, v in c.cookies.items()
            ])  # fmt: skip
        if voice:  # озвучка реплик собеседника (переключатель «голос» в панели разговора)
            ctx.add_init_script("try { localStorage.setItem('aiskra.call.voice', '1') } catch (e) {}")
        page = ctx.new_page()
        page.set_default_timeout(TIMEOUT_MS)
        self.watch(page, login or "аноним")
        self.contexts.append(ctx)
        self.pages.append(page)
        return page

    def watch(self, page: Page, who: str) -> None:
        def on_console(m: ConsoleMessage) -> None:
            if m.type == "error" and not any(s in m.text for s in IGNORED_CONSOLE):
                self.errors.add(f"[{who}] console.error {page.url}: {m.text[:500]}")
            else:
                self.errors.log.append(f"[{who}] console.{m.type} {page.url}: {m.text[:500]}")

        def on_response(r: Response) -> None:
            if "/api/" in r.url and r.status >= 500:
                self.errors.add(f"[{who}] HTTP {r.status} {r.request.method} {r.url}")

        page.on("console", on_console)
        page.on("pageerror", lambda e: self.errors.add(f"[{who}] pageerror {page.url}: {str(e)[:500]}"))
        page.on("response", on_response)
        page.on("dialog", lambda d: d.accept())


@pytest.fixture
def ui(browser: Browser, stand: Stand, request: pytest.FixtureRequest) -> Iterator[Session]:
    session = Session(browser, stand, BrowserErrors())
    yield session
    failed = any(getattr(request.node, f"rep_{w}", None) and getattr(request.node, f"rep_{w}").failed
                 for w in ("setup", "call"))  # fmt: skip
    errors = list(session.errors.items)
    if failed or errors:
        out = ARTIFACTS / re.sub(r"[^\w.-]+", "_", request.node.nodeid.split("::", 1)[-1])
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True, exist_ok=True)
        for i, page in enumerate(session.pages):
            try:
                page.screenshot(path=str(out / f"page{i}.png"), full_page=True)
            except Exception as e:  # страница уже закрыта
                (out / f"page{i}.txt").write_text(str(e), "utf-8")
        (out / "console.json").write_text(json.dumps(session.errors.log, ensure_ascii=False, indent=1), "utf-8")
        for name in ("backend.log", "frontend.log"):
            src = stand.home / name
            if src.exists():
                (out / name).write_text(src.read_text("utf-8", errors="replace")[-20000:], "utf-8")
    for ctx in session.contexts:
        ctx.close()
    if errors and not failed:
        pytest.fail("Ошибки в браузере:\n" + "\n".join(errors), pytrace=False)


Wait = Callable[[], bool]


def eventually(check: Wait, timeout: float = 15.0, step: float = 0.25, what: str = "условие") -> None:
    """Ожидание состояния на сервере (статусы, оценки), которое интерфейс получает опросом."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(step)
    raise AssertionError(f"не дождались: {what}")
