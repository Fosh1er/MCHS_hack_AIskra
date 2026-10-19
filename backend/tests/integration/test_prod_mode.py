"""F6.3 (ADR-0015) через HTTP: режим prod — без демо-входа и `/dev`, Swagger и схема API только администратору,
cookie Secure; `/health` отдаёт режим, версию и время старта; небезопасный prod не создаётся вовсе."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from aiskra.main import create_app
from aiskra.platform.settings import Settings
from aiskra.platform.startup_checks import UnsafeConfigError
from tests.integration.conftest import login


def prod(settings: Settings, **kw: object) -> Settings:
    """prod на SQLite тестов: пароля БД нет, cookie Secure — как в docker compose за nginx с TLS."""
    return settings.model_copy(update={"app_env": "prod", "session_cookie_secure": True, **kw})


def test_prod_has_no_demo_or_dev_routes_and_swagger_is_admin_only(settings: Settings) -> None:
    app = create_app(prod(settings, version="1a2b3c4"))
    # роутеры подключаются лениво: маршруты схемы — из openapi(), служебные (/docs) — из app.routes
    paths = set(app.openapi()["paths"]) | {p for r in app.routes if (p := getattr(r, "path", ""))}
    assert not any(p.startswith("/dev") for p in paths)
    assert not any("demo" in p for p in paths)
    with TestClient(app, base_url="https://testserver") as anon:
        for url in ("/docs", "/openapi.json"):
            r = anon.get(url)
            assert r.status_code == 401 and r.json()["error"] == "unauthenticated", url
        assert anon.get("/api/v1/auth/demo-accounts").status_code == 404
        assert anon.post("/api/v1/auth/demo-login", json={"login": "teacher"}).status_code == 404
        assert anon.get("/dev/ai").status_code == 404

    with TestClient(app, base_url="https://testserver") as student:
        login(student, "student")
        assert student.get("/docs").status_code == 403 and student.get("/openapi.json").status_code == 403

    with TestClient(app, base_url="https://testserver") as admin:
        r = admin.post("/api/v1/auth/login", json={"login": "admin", "password": "Test-Pass-2026", "arm_number": "1"})
        assert "secure" in r.headers["set-cookie"].lower()
        schema = admin.get("/openapi.json")
        assert schema.status_code == 200 and schema.json()["info"]["version"] == "1a2b3c4"
        assert "/api/v1/auth/login" in schema.json()["paths"] and "/docs" not in schema.json()["paths"]
        assert not any(p.startswith("/dev") or "demo" in p for p in schema.json()["paths"])
        docs = admin.get("/docs")
        assert docs.status_code == 200 and "swagger-ui" in docs.text and "/openapi.json" in docs.text


def test_access_denied_to_swagger_is_audited(settings: Settings) -> None:
    app = create_app(prod(settings))
    with TestClient(app, base_url="https://testserver") as c:
        login(c, "teacher")
        assert c.get("/docs").status_code == 403
        login(c, "admin")
        items = c.get("/api/v1/audit", params={"page_size": 50}).json()["items"]
    assert any(i["event"] == "auth.access_denied" and "/docs" in (i["description"] or "") for i in items)


@pytest.mark.parametrize("env", ["demo", "dev"])
def test_demo_and_dev_keep_public_swagger(settings: Settings, env: str) -> None:
    with TestClient(create_app(settings.model_copy(update={"app_env": env}))) as c:
        assert c.get("/docs").status_code == 200 and c.get("/openapi.json").status_code == 200


def test_expose_docs_false_hides_swagger_in_prod_too(settings: Settings) -> None:
    app = create_app(prod(settings, expose_docs=False))
    with TestClient(app, base_url="https://testserver") as c:
        login(c, "admin")
        assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404


def test_health_reports_env_version_and_start_time(settings: Settings) -> None:
    before = datetime.now(UTC)
    with TestClient(create_app(prod(settings, version="0f6e3d2"))) as c:
        h = c.get("/health").json()
    assert h["env"] == "prod" and h["version"] == "0f6e3d2" and h["status"] == "ok"
    started = datetime.fromisoformat(h["started_at"])
    assert before - timedelta(seconds=1) <= started <= datetime.now(UTC)
    with TestClient(create_app(settings)) as c:  # переменная не задана — unknown
        h = c.get("/health").json()
    assert h["env"] == "dev" and h["version"] == "unknown"


def test_unsafe_prod_is_not_created(settings: Settings) -> None:
    """Fail fast: приложение с cookie без Secure в prod не создаётся, сообщение — по-русски и с подсказкой."""
    with pytest.raises(UnsafeConfigError, match=r"\[cookie_insecure\].*AISKRA_SESSION_COOKIE_SECURE=true"):
        create_app(settings.model_copy(update={"app_env": "prod"}))
