"""F2: демо-учётки на странице входа и демо-вход одной кнопкой (режимы окружения ADR-0015)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from aiskra.cli import create_user
from aiskra.demo_seed import DEMO_USERS
from aiskra.main import create_app
from aiskra.platform.settings import Settings
from aiskra.shared.security import Role
from tests.integration.conftest import PASSWORD, login

ACCOUNTS = "/api/v1/auth/demo-accounts"
DEMO_LOGIN = "/api/v1/auth/demo-login"
DEMO_PASSWORD = "Demo-Stand-2026"  # синтетический пароль только для тестов


@pytest.fixture
def demo_settings(settings: Settings) -> Settings:
    """База с пользователями conftest (admin, teacher, student) и двумя демо-учётками стенда."""
    for login_, name, number in (("op1", "Кузнецов Олег Павлович", "101"), ("dds1", "Орлова Мария Игоревна", "201")):
        asyncio.run(
            create_user(
                settings, login=login_, full_name=name, role=Role.STUDENT, password=PASSWORD, operator_number=number
            )
        )
    return settings.model_copy(update={"app_env": "demo", "demo_password": SecretStr(DEMO_PASSWORD)})


def stand(settings: Settings, **update: Any) -> TestClient:
    return TestClient(create_app(settings.model_copy(update=update)))


@pytest.fixture
def demo(demo_settings: Settings) -> Iterator[TestClient]:
    with stand(demo_settings) as c:
        yield c


def test_demo_users_have_no_admin_and_say_what_to_see() -> None:
    assert len(DEMO_USERS) == 5 and all(u.role is not Role.ADMIN for u in DEMO_USERS)
    assert all(u.title and 1 <= len(u.hint) <= 2 and u.arm_number for u in DEMO_USERS)


def test_accounts_listed_without_passwords(demo: TestClient) -> None:
    r = demo.get(ACCOUNTS)
    assert r.status_code == 200
    body = r.json()
    # только учётки DEMO_USERS, которые есть в базе: teacher и op1, dds1 из conftest/фикстуры; op2, dds2 — нет
    assert [a["login"] for a in body["accounts"]] == ["teacher", "op1", "dds1"]
    op1 = body["accounts"][1]
    assert op1 == {
        "login": "op1",
        "role": "student",
        "title": "Оператор 112",
        "full_name": "Кузнецов Олег Павлович",
        "hint": list(next(u.hint for u in DEMO_USERS if u.login == "op1")),
        "arm_number": "101",
    }
    assert body["password"] is None
    assert DEMO_PASSWORD not in r.text and PASSWORD not in r.text and "admin" not in r.text


def test_demo_login_opens_regular_session_and_is_audited(demo: TestClient, demo_settings: Settings) -> None:
    r = demo.post(DEMO_LOGIN, json={"login": "OP1"})
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["login"] == "op1" and me["role"] == "student" and me["arm_number"] == "101"
    assert "training.participate" in me["permissions"] and me["expires_at"]
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert demo.get("/api/v1/auth/me").json()["login"] == "op1"

    with stand(demo_settings) as admin:
        login(admin, "admin")
        items = admin.get("/api/v1/audit", params={"event": "auth.demo_login", "page_size": 50}).json()["items"]
    assert len(items) == 1 and items[0]["actor_login"] == "op1" and items[0]["arm_number"] == "101"
    assert items[0]["event_title"] == "Вход на демо-стенде без пароля"


@pytest.mark.parametrize("who", ["admin", "student", "ghost", "op2"])
def test_only_demo_accounts_can_enter(demo: TestClient, who: str) -> None:
    """admin — не демо-учётка; student — есть в базе, но не в DEMO_USERS; op2 — в DEMO_USERS, но нет в базе."""
    r = demo.post(DEMO_LOGIN, json={"login": who})
    assert r.status_code == 404 and r.json()["error"] == "demo_account_not_found"
    assert demo.get("/api/v1/auth/me").status_code == 401


def test_bad_body_is_422(demo: TestClient) -> None:
    assert demo.post(DEMO_LOGIN, json={"login": ""}).status_code == 422
    assert demo.post(DEMO_LOGIN, json={}).status_code == 422


@pytest.mark.parametrize("show", [False, True])
def test_prod_has_no_demo_routes(demo_settings: Settings, show: bool) -> None:
    with stand(demo_settings, app_env="prod", demo_show_password=show, session_cookie_secure=True) as c:
        assert c.get(ACCOUNTS).status_code == 404
        assert c.post(DEMO_LOGIN, json={"login": "op1"}).status_code == 404
        assert c.get("/api/v1/auth/me").status_code == 401
        assert c.get("/health").json()["env"] == "prod"
        assert c.get("/openapi.json").status_code == 401  # F6.3: схема API в prod — только администратору
        assert not [p for p in c.app.openapi()["paths"] if "demo" in p]  # type: ignore[attr-defined]


def test_dev_has_demo_routes(demo_settings: Settings) -> None:
    with stand(demo_settings, app_env="dev") as c:
        assert c.get("/health").json()["env"] == "dev"
        assert c.get(ACCOUNTS).status_code == 200
        assert c.post(DEMO_LOGIN, json={"login": "teacher"}).json()["role"] == "teacher"


def test_password_shown_only_with_flag(demo_settings: Settings) -> None:
    with stand(demo_settings, demo_show_password=True) as c:
        assert c.get(ACCOUNTS).json()["password"] == DEMO_PASSWORD
        assert c.get("/health").json()["env"] == "demo"
    with stand(demo_settings, demo_show_password=True, demo_password=None) as c:
        assert c.get(ACCOUNTS).json()["password"] is None


def test_blocked_account_hidden_and_cannot_enter(demo: TestClient, demo_settings: Settings) -> None:
    with stand(demo_settings) as admin:
        login(admin, "admin")
        users = admin.get("/api/v1/users", params={"q": "op1"}).json()["items"]
        assert admin.post(f"/api/v1/users/{users[0]['id']}/block", json={"reason": "тест"}).status_code == 204
    assert "op1" not in [a["login"] for a in demo.get(ACCOUNTS).json()["accounts"]]
    r = demo.post(DEMO_LOGIN, json={"login": "op1"})
    assert r.status_code == 401 and r.json()["error"] == "account_blocked"


def test_password_lockout_does_not_close_demo_login(demo: TestClient) -> None:
    """Временную блокировку неверными паролями на публичном стенде может включить кто угодно."""
    for _ in range(3):  # login_max_attempts=3 в тестовых настройках
        demo.post("/api/v1/auth/login", json={"login": "teacher", "password": "wrong-pass"})
    r = demo.post("/api/v1/auth/login", json={"login": "teacher", "password": PASSWORD})
    assert r.json()["error"] == "account_locked"
    assert demo.post(DEMO_LOGIN, json={"login": "teacher"}).status_code == 200


def test_demo_login_rate_limited_per_ip(demo: TestClient) -> None:
    for i in range(10):  # считаются все запросы, и удачные, и нет
        r = demo.post(DEMO_LOGIN, json={"login": "op1" if i % 2 else "ghost"})
        assert r.status_code in (200, 404)
    r = demo.post(DEMO_LOGIN, json={"login": "op1"})
    assert r.status_code == 429 and r.json()["error"] == "too_many_requests"
    assert "демо-входов" in r.json()["message"]
    # обычный вход по паролю этим лимитом не затронут
    assert demo.post("/api/v1/auth/login", json={"login": "op1", "password": PASSWORD}).status_code == 200


def test_demo_login_keeps_onboarding_progress(demo: TestClient, demo_settings: Settings) -> None:
    """RF2-06: демо-вход ничего не сбрасывает — пройденные подсказки другого эксперта под той же учёткой остаются."""
    assert demo.post(DEMO_LOGIN, json={"login": "op1"}).status_code == 200
    assert demo.post("/api/v1/auth/onboarding", json={"action": "dismiss"}).status_code == 200
    with stand(demo_settings) as other:
        assert other.post(DEMO_LOGIN, json={"login": "op1"}).status_code == 200
        assert other.get("/api/v1/auth/onboarding").json()["dismissed"] is True
    assert demo.get("/api/v1/auth/me").status_code == 200  # первая сессия не отозвана
