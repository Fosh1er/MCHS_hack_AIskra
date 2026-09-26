"""П. 6.2 через HTTP: закрытость всех маршрутов, заголовки, ограничение входа по IP, ответ 500, ретеншн аудита."""

import asyncio
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from aiskra.main import create_app
from aiskra.modules.audit.infrastructure.models import AuditLogModel
from aiskra.platform.db import create_engine, create_session_factory
from aiskra.platform.settings import Settings
from tests.integration.conftest import PASSWORD, login

PUBLIC = {("POST", "/api/v1/auth/login")}


def test_every_api_route_requires_session(settings: Settings) -> None:
    app = create_app(settings)
    paths = app.openapi()["paths"]  # полный перечень маршрутов с префиксами (роутеры подключаются лениво)
    routes = [(m.upper(), p) for p, ops in paths.items() if p.startswith("/api/") for m in ops]
    assert len(routes) > 80  # защитный порог: маршруты действительно перебираются
    with TestClient(app) as c:
        for method, path in routes:
            if (method, path) in PUBLIC:
                continue
            url = re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000000", path)
            r = c.request(method, url, json={})
            assert r.status_code == 401, f"{method} {path} → {r.status_code}"


def test_security_headers_and_hsts(settings: Settings) -> None:
    with TestClient(create_app(settings), base_url="https://testserver") as c:
        r = c.get("/api/v1/auth/me")
        h = r.headers
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "SAMEORIGIN"
        assert h["referrer-policy"] == "same-origin" and "microphone=(self)" in h["permissions-policy"]
        assert h["cache-control"] == "no-store" and h["strict-transport-security"].startswith("max-age=")
    with TestClient(create_app(settings)) as c:  # по HTTP HSTS не отдаётся
        assert "strict-transport-security" not in c.get("/health").headers


def test_login_throttled_per_ip(client: TestClient) -> None:
    for _ in range(20):
        r = client.post("/api/v1/auth/login", json={"login": "nobody", "password": "wrong-pass", "arm_number": "1"})
        assert r.status_code == 401
    r = client.post("/api/v1/auth/login", json={"login": "student", "password": PASSWORD, "arm_number": "1"})
    assert r.status_code == 429 and r.json()["error"] == "too_many_requests"


def test_success_resets_ip_counter(client: TestClient) -> None:
    for _ in range(15):
        client.post("/api/v1/auth/login", json={"login": "nobody", "password": "wrong-pass", "arm_number": "1"})
    login(client, "student")
    for _ in range(15):
        assert client.post("/api/v1/auth/login", json={"login": "nobody", "password": "x" * 8}).status_code == 401


def test_unexpected_error_hides_details(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("секрет: postgresql://user:pass@db/aiskra")

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/boom")
    assert r.status_code == 500 and r.json() == {"error": "internal_error", "message": "Внутренняя ошибка сервера"}
    assert "секрет" not in r.text


def test_docs_can_be_hidden(settings: Settings) -> None:
    with TestClient(create_app(settings.model_copy(update={"expose_docs": False}))) as c:
        assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404


def test_audit_retention(settings: Settings, admin: TestClient, app_client: Callable[[], TestClient]) -> None:
    async def add_old() -> None:
        engine = create_engine(settings.database_url)
        async with create_session_factory(engine)() as s:
            now = datetime.now(UTC)
            for days, text in ((200, "полгода с лишним"), (400, "больше года")):
                s.add(AuditLogModel(at=now - timedelta(days=days), event="auth.logout", description=text))
            await s.commit()
        await engine.dispose()

    asyncio.run(add_old())
    dry = admin.post("/api/v1/audit/purge", params={"dry_run": True}).json()
    assert dry["retention_days"] == 365 and dry["deleted"] == 1 and dry["dry_run"]
    assert admin.put("/api/v1/system/settings/audit", json={"values": {"retention_days": 90}}).status_code == 422
    r = admin.post("/api/v1/audit/purge").json()
    assert r["deleted"] == 1 and not r["dry_run"]
    items = admin.get("/api/v1/audit", params={"page_size": 100}).json()["items"]
    texts = {i["description"] for i in items}
    assert "полгода с лишним" in texts and "больше года" not in texts  # моложе 6 месяцев+ — остаётся
    assert any(i["event"] == "audit.purged" for i in items)
    teacher = app_client()
    login(teacher, "teacher")
    assert teacher.post("/api/v1/audit/purge").status_code == 403


def test_session_cookie_flags(settings: Settings) -> None:
    for secure in (False, True):
        app = create_app(settings.model_copy(update={"session_cookie_secure": secure}))
        with TestClient(app, base_url="https://testserver") as c:
            r = c.post("/api/v1/auth/login", json={"login": "student", "password": PASSWORD, "arm_number": "1"})
        cookie = r.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie
        assert ("secure" in cookie) is secure
        assert PASSWORD.lower() not in r.text.lower()  # пароль не возвращается и не отражается


def test_dictionaries_cacheable_and_compressed(settings: Settings) -> None:
    """6.1: справочники кешируются браузером (без ПДн), большие ответы сжимаются; прочий API — no-store."""
    with TestClient(create_app(settings)) as c:
        login(c, "student")
        r = c.get("/api/v1/dictionaries/card-types", headers={"Accept-Encoding": "gzip"})
        assert r.status_code == 200 and r.headers["cache-control"] == "private, max-age=600"
        big = c.get("/api/v1/auth/me", headers={"Accept-Encoding": "gzip"})
        assert big.headers["cache-control"] == "no-store"
        journal = c.get("/api/v1/incidents/journal", params={"page_size": 100}, headers={"Accept-Encoding": "gzip"})
        if len(journal.content) > 1024:
            assert journal.headers.get("content-encoding") == "gzip"
